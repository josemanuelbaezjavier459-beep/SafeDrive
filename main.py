from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.textinput import TextInput
from kivy.utils import platform as kivy_platform
from kivy.uix.widget import Widget
from datetime import datetime
import asyncio
import json
import queue
import re
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

IS_ANDROID = kivy_platform == "android"
IS_DESKTOP = not IS_ANDROID

if IS_DESKTOP:
    try:
        from bleak import BleakClient, BleakScanner
        from bleak.backends.winrt.util import allow_sta
    except Exception:
        BleakClient = None
        BleakScanner = None
        allow_sta = None

    try:
        import serial
        from serial.tools import list_ports
    except Exception:
        serial = None
        list_ports = None
else:
    BleakClient = None
    BleakScanner = None
    allow_sta = None
    serial = None
    list_ports = None

if IS_ANDROID:
    try:
        from jnius import autoclass, PythonJavaClass, java_method, cast
        from android.permissions import request_permissions, Permission
    except Exception:
        autoclass = None
        PythonJavaClass = object
        cast = None
        request_permissions = None
        Permission = None

    class AndroidScanCallback(PythonJavaClass):
        __javainterfaces__ = ["android/bluetooth/le/ScanCallback"]
        __javacontext__ = "app"

        @java_method("(ILandroid/bluetooth/le/ScanResult;)V")
        def onScanResult(self, callback_type, result):
            app = App.get_running_app()
            if app:
                app._android_handle_scan_result(result)

        @java_method("(Ljava/util/List;)V")
        def onBatchScanResults(self, results):
            app = App.get_running_app()
            if not app:
                return
            for result in results:
                app._android_handle_scan_result(result)

        @java_method("(I)V")
        def onScanFailed(self, error_code):
            app = App.get_running_app()
            if app:
                app.bluetooth_status_queue.put(("error", "ANDROID", f"Scan BLE fallo: {error_code}", "Android BLE"))

    class AndroidGattCallback(PythonJavaClass):
        __javainterfaces__ = ["android/bluetooth/BluetoothGattCallback"]
        __javacontext__ = "app"

        @java_method("(Landroid/bluetooth/BluetoothGatt;II)V")
        def onConnectionStateChange(self, gatt, status, new_state):
            app = App.get_running_app()
            if app:
                app._android_on_connection_state_change(gatt, status, new_state)

        @java_method("(Landroid/bluetooth/BluetoothGatt;I)V")
        def onServicesDiscovered(self, gatt, status):
            app = App.get_running_app()
            if app:
                app._android_on_services_discovered(gatt, status)

        @java_method("(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;)V")
        def onCharacteristicChanged(self, gatt, characteristic):
            app = App.get_running_app()
            if app:
                app._android_on_characteristic_changed(characteristic)

        # Android 13+ callback signature includes the value bytes directly.
        @java_method("(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;[B)V")
        def onCharacteristicChanged2(self, gatt, characteristic, value):
            app = App.get_running_app()
            if app:
                app._android_on_characteristic_changed(characteristic, value=value)


class RoundedPanel(BoxLayout):
    """BoxLayout with rounded colored background."""

    def __init__(self, bg_color=(1, 1, 1, 1), radius=0, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.radius = [radius, radius, radius, radius]
        with self.canvas.before:
            self._bg_color = Color(*self.bg_color)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=self.radius)
        self.bind(pos=self._update_bg, size=self._update_bg)

    def _update_bg(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size


class PlainLink(ButtonBehavior, Label):
    """Simple text-only clickable label."""


class RoundedButton(Button):
    """Button with rounded background shape."""

    def __init__(self, bg_color=(0.2, 0.2, 0.8, 1), radius=0, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self._btn_bg_color_value = bg_color
        self._btn_radius = [radius, radius, radius, radius]
        with self.canvas.before:
            self._btn_bg_color = Color(*self._btn_bg_color_value)
            self._btn_bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=self._btn_radius)
        self.bind(pos=self._update_btn_bg, size=self._update_btn_bg)

    def _update_btn_bg(self, *_):
        self._btn_bg_rect.pos = self.pos
        self._btn_bg_rect.size = self.size


class InputScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation="horizontal")

        left_panel = RoundedPanel(
            orientation="vertical",
            bg_color=(0 / 255, 98 / 255, 53 / 255, 1),
            radius=0,
            size_hint_x=0.4,
            padding=(dp(24), dp(24), dp(24), dp(24)),
        )
        left_panel.add_widget(Widget())
        left_content = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None, height=dp(120))
        left_content.add_widget(
            Label(
                text="Safe Drive",
                font_size=dp(36),
                bold=True,
                color=(1, 1, 1, 1),
                halign="left",
                valign="middle",
            )
        )
        left_content.add_widget(
            Label(
                text="Complete sus datos en el panel derecho para iniciar sesion",
                font_size=dp(18),
                color=(1, 1, 1, 1),
                halign="left",
                valign="middle",
            )
        )
        for child in left_content.children:
            child.bind(size=lambda instance, _: setattr(instance, "text_size", instance.size))
        left_panel.add_widget(left_content)
        left_panel.add_widget(Widget())
        root.add_widget(left_panel)

        right_panel = BoxLayout(
            orientation="vertical",
            size_hint_x=0.6,
            padding=(dp(64), dp(64), dp(64), dp(48)),
            spacing=dp(16),
        )
        right_panel.add_widget(Widget(size_hint_y=0.7))

        form_box = BoxLayout(orientation="vertical", spacing=dp(14), size_hint_y=None, height=dp(420))
        form_box.add_widget(
            Label(
                text="Iniciar sesion",
                font_size=dp(48),
                bold=True,
                color=(0 / 255, 98 / 255, 53 / 255, 1),
                size_hint_y=None,
                height=dp(64),
            )
        )
        form_box.add_widget(
            Label(
                text="Ingrese sus credenciales para continuar",
                font_size=dp(22),
                color=(0.45, 0.45, 0.45, 1),
                size_hint_y=None,
                height=dp(34),
            )
        )

        self.email_input = TextInput(
            hint_text="Correo electronico",
            multiline=False,
            size_hint_y=None,
            height=dp(60),
            padding=(dp(16), dp(16), dp(16), dp(16)),
            background_normal="",
            background_active="",
            background_color=(0.87, 0.87, 0.87, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            cursor_color=(0.2, 0.2, 0.2, 1),
        )
        self.password_input = TextInput(
            hint_text="Contrasena",
            multiline=False,
            password=True,
            size_hint_y=None,
            height=dp(60),
            padding=(dp(16), dp(16), dp(16), dp(16)),
            background_normal="",
            background_active="",
            background_color=(0.87, 0.87, 0.87, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            cursor_color=(0.2, 0.2, 0.2, 1),
        )
        self.message_label = Label(
            text="",
            color=(0.72, 0.11, 0.11, 1),
            size_hint_y=None,
            height=dp(22),
            font_size=dp(16),
        )
        self.login_btn = Button(
            text="Ingresar",
            size_hint_y=None,
            height=dp(54),
            background_normal="",
            background_down="",
            background_color=(0 / 255, 98 / 255, 53 / 255, 1),
            color=(1, 1, 1, 1),
            bold=True,
            font_size=dp(26),
        )
        self.login_btn.bind(on_release=self.on_go)

        remember_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8))
        self.remember_checkbox = CheckBox(size_hint=(None, None), size=(dp(24), dp(24)), color=(0.2, 0.2, 0.2, 1))
        remember_label = Label(
            text="Recuerdame",
            size_hint_x=None,
            width=dp(120),
            color=(0.35, 0.35, 0.35, 1),
            halign="left",
            valign="middle",
        )
        remember_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        remember_row.add_widget(self.remember_checkbox)
        remember_row.add_widget(remember_label)
        remember_row.add_widget(Widget())

        form_box.add_widget(self.email_input)
        form_box.add_widget(self.password_input)
        form_box.add_widget(remember_row)
        form_box.add_widget(self.message_label)
        form_box.add_widget(Widget(size_hint_y=0.1))
        form_box.add_widget(self.login_btn)
        form_box.add_widget(Widget(size_hint_y=0.45))

        register_link = PlainLink(
            text="No tienes cuenta? Registrate",
            color=(0.35, 0.35, 0.35, 1),
            font_size=dp(17),
            size_hint_y=None,
            height=dp(24),
        )
        register_link.bind(on_release=lambda *_: self._set_message("Registro no disponible aun"))
        form_box.add_widget(register_link)

        right_panel.add_widget(form_box)
        right_panel.add_widget(Widget())
        root.add_widget(right_panel)
        self.add_widget(root)

    def _set_message(self, message):
        self.message_label.text = message

    def on_go(self, *_):
        email = self.email_input.text.strip()
        password = self.password_input.text.strip()
        if not email or not password:
            self._set_message("Debe completar correo y contrasena")
            return

        app = App.get_running_app()
        app.user_name = email
        app.remember_me = self.remember_checkbox.active
        app.store.put("user", email=email)
        app.store.put("settings", remember_me=app.remember_me)
        self._set_message("")
        self.manager.current = "welcome"

    def on_pre_enter(self):
        self.email_input.text = ""
        self.password_input.text = ""
        app = App.get_running_app()
        self.remember_checkbox.active = getattr(app, "remember_me", False)
        self._set_message("")


class WelcomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._is_formatting_number = False
        self.editing_index = None
        self._build_ui()

    def _build_ui(self):
        root = RoundedPanel(
            orientation="vertical",
            bg_color=(0 / 255, 203 / 255, 123 / 255, 1),
            padding=(dp(20), dp(16), dp(20), dp(16)),
            spacing=dp(12),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(66), spacing=dp(12))
        self.greeting = Label(
            text="Bienvenido a SafeDrive",
            font_size=dp(38),
            bold=True,
            color=(0, 0, 0, 1),
            halign="center",
            valign="middle",
        )
        self.greeting.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        pair_btn = RoundedButton(
            text="conectar\ndispositivo",
            size_hint=(None, 1),
            width=dp(170),
            bg_color=(0.12, 0.08, 0.78, 1),
            radius=dp(20),
            color=(1, 1, 1, 1),
            bold=True,
        )
        pair_btn.bind(on_release=lambda *_: self.go_bluetooth())
        history_btn = RoundedButton(
            text="Historial",
            size_hint=(None, 1),
            width=dp(150),
            bg_color=(0.45, 0.45, 0.45, 1),
            radius=dp(20),
            color=(1, 1, 1, 1),
            bold=True,
        )
        history_btn.bind(on_release=lambda *_: self.go_history())
        top_row.add_widget(history_btn)
        top_row.add_widget(self.greeting)
        top_row.add_widget(pair_btn)
        root.add_widget(top_row)

        title_bar = RoundedPanel(
            orientation="vertical",
            bg_color=(0 / 255, 103 / 255, 63 / 255, 1),
            radius=dp(18),
            size_hint_y=None,
            height=dp(44),
        )
        title_bar.add_widget(Label(text="Listado de Contactos", font_size=dp(24), bold=True, color=(0, 0, 0, 1)))
        root.add_widget(title_bar)

        contacts_box = RoundedPanel(
            orientation="vertical",
            bg_color=(0.75, 0.73, 0.88, 1),
            radius=dp(20),
            padding=(dp(12), dp(12), dp(12), dp(12)),
            spacing=dp(8),
        )

        add_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        self.name_input = TextInput(
            hint_text="Nombre",
            multiline=False,
            background_normal="",
            background_active="",
            background_color=(1, 1, 1, 1),
            foreground_color=(0, 0, 0, 1),
            padding=(dp(10), dp(10), dp(10), dp(10)),
        )
        self.number_input = TextInput(
            hint_text="Numero",
            multiline=False,
            background_normal="",
            background_active="",
            background_color=(1, 1, 1, 1),
            foreground_color=(0, 0, 0, 1),
            padding=(dp(10), dp(10), dp(10), dp(10)),
            size_hint_x=0.7,
        )
        self.number_input.bind(text=self._on_number_text)
        self.add_btn = Button(
            text="Anadir",
            size_hint_x=None,
            width=dp(96),
            background_normal="",
            background_down="",
            background_color=(0 / 255, 103 / 255, 63 / 255, 1),
            color=(1, 1, 1, 1),
            bold=True,
        )
        self.add_btn.bind(on_release=self.add_contact)
        self.cancel_edit_btn = Button(
            text="Cancelar",
            size_hint_x=None,
            width=dp(110),
            background_normal="",
            background_down="",
            background_color=(0.55, 0.55, 0.55, 1),
            color=(1, 1, 1, 1),
            bold=True,
            opacity=0,
            disabled=True,
        )
        self.cancel_edit_btn.bind(on_release=lambda *_: self._exit_edit_mode())
        add_row.add_widget(self.name_input)
        add_row.add_widget(self.number_input)
        add_row.add_widget(self.add_btn)
        add_row.add_widget(self.cancel_edit_btn)
        contacts_box.add_widget(add_row)

        self.message_label = Label(
            text="",
            size_hint_y=None,
            height=dp(22),
            color=(0.72, 0.11, 0.11, 1),
            font_size=dp(14),
        )
        contacts_box.add_widget(self.message_label)

        self.contacts_container = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.contacts_container.bind(minimum_height=self.contacts_container.setter("height"))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(8))
        scroll.add_widget(self.contacts_container)
        contacts_box.add_widget(scroll)
        root.add_widget(contacts_box)

        close_btn = Button(
            text="Cerrar Sesion",
            size_hint_y=None,
            height=dp(54),
            background_normal="",
            background_down="",
            background_color=(0.85, 0, 0, 1),
            color=(0, 0, 0, 1),
            bold=True,
            font_size=dp(30),
        )
        close_btn.bind(on_release=lambda *_: self.go_back())
        root.add_widget(close_btn)
        self.add_widget(root)

    def on_pre_enter(self):
        self.greeting.text = "Bienvenido a SafeDrive"
        self._exit_edit_mode(clear_message=True)
        self.refresh_contacts()

    def add_contact(self, *_):
        name = self.name_input.text.strip()
        number = self.number_input.text.strip()
        number_digits = "".join(ch for ch in number if ch.isdigit())
        if not name or not number:
            self.message_label.text = "Ingrese nombre y numero"
            return
        if len(number_digits) != 10:
            self.message_label.text = "El numero debe tener 10 digitos"
            return

        app = App.get_running_app()
        contact_payload = {"name": name, "number": f"+1 {self._format_phone_number(number_digits)}"}
        if self.editing_index is None:
            app.contacts.append(contact_payload)
        else:
            app.contacts[self.editing_index] = contact_payload
        app.save_contacts()
        self._exit_edit_mode(clear_message=True)
        self.refresh_contacts()

    def _on_number_text(self, *_):
        if self._is_formatting_number:
            return

        digits = "".join(ch for ch in self.number_input.text if ch.isdigit())[:10]
        formatted = self._format_phone_number(digits)
        if self.number_input.text != formatted:
            self._is_formatting_number = True
            self.number_input.text = formatted
            self.number_input.cursor = (len(formatted), 0)
            self._is_formatting_number = False

    @staticmethod
    def _format_phone_number(digits):
        if len(digits) <= 3:
            return digits
        if len(digits) <= 6:
            return f"{digits[:3]}-{digits[3:]}"
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"

    def refresh_contacts(self):
        self.contacts_container.clear_widgets()
        app = App.get_running_app()
        if not app.contacts:
            self.contacts_container.add_widget(
                Label(
                    text="No hay contactos aun",
                    size_hint_y=None,
                    height=dp(40),
                    color=(0.18, 0.18, 0.18, 1),
                )
            )
            return

        for index, item in enumerate(app.contacts):
            display_number = item.get("number", "")
            if display_number and not display_number.startswith("+1 "):
                display_number = f"+1 {display_number}"
            row = RoundedPanel(
                orientation="horizontal",
                bg_color=(1, 1, 1, 1),
                radius=dp(14),
                size_hint_y=None,
                height=dp(42),
                padding=(dp(10), dp(8), dp(10), dp(8)),
            )
            buttons_box = BoxLayout(
                orientation="horizontal",
                size_hint=(None, 1),
                width=dp(170),
                spacing=dp(6),
            )
            edit_btn = Button(
                text="Editar",
                background_normal="",
                background_down="",
                background_color=(0.13, 0.35, 0.83, 1),
                color=(1, 1, 1, 1),
                bold=True,
            )
            delete_btn = Button(
                text="Eliminar",
                background_normal="",
                background_down="",
                background_color=(0.85, 0.1, 0.1, 1),
                color=(1, 1, 1, 1),
                bold=True,
            )
            edit_btn.bind(on_release=lambda _, idx=index: self._start_edit_contact(idx))
            delete_btn.bind(on_release=lambda _, idx=index: self._delete_contact(idx))
            buttons_box.add_widget(edit_btn)
            buttons_box.add_widget(delete_btn)

            row_label = Label(
                text=f"{item['name']} - {display_number}",
                color=(0, 0, 0, 1),
                bold=True,
                halign="left",
                valign="middle",
            )
            row_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            row.add_widget(row_label)
            row.add_widget(buttons_box)
            self.contacts_container.add_widget(row)

    def _start_edit_contact(self, index):
        app = App.get_running_app()
        if index < 0 or index >= len(app.contacts):
            return
        item = app.contacts[index]
        self.editing_index = index
        self.name_input.text = item.get("name", "")
        number_text = item.get("number", "").replace("+1 ", "")
        self.number_input.text = number_text
        self.add_btn.text = "Guardar"
        self.cancel_edit_btn.opacity = 1
        self.cancel_edit_btn.disabled = False
        self.message_label.text = "Editando contacto"

    def _delete_contact(self, index):
        app = App.get_running_app()
        if index < 0 or index >= len(app.contacts):
            return
        app.contacts.pop(index)
        app.save_contacts()
        if self.editing_index == index:
            self._exit_edit_mode(clear_message=True)
        elif self.editing_index is not None and self.editing_index > index:
            self.editing_index -= 1
        self.refresh_contacts()

    def _exit_edit_mode(self, clear_message=False):
        self.editing_index = None
        self.name_input.text = ""
        self.number_input.text = ""
        self.add_btn.text = "Anadir"
        self.cancel_edit_btn.opacity = 0
        self.cancel_edit_btn.disabled = True
        if clear_message:
            self.message_label.text = ""

    def go_back(self):
        self.manager.current = "input"

    def go_history(self):
        self.manager.current = "history"

    def go_bluetooth(self):
        self.manager.current = "bluetooth"


class HistoryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_ui()

    def _build_ui(self):
        root = RoundedPanel(
            orientation="vertical",
            bg_color=(0 / 255, 203 / 255, 123 / 255, 1),
            padding=(dp(20), dp(16), dp(20), dp(16)),
            spacing=dp(12),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(66), spacing=dp(12))
        clear_history_btn = Button(
            text="Limpiar Historial",
            size_hint=(None, 1),
            width=dp(220),
            background_normal="",
            background_down="",
            background_color=(0.85, 0.1, 0.1, 1),
            color=(1, 1, 1, 1),
            bold=True,
            font_size=dp(18),
        )
        clear_history_btn.bind(on_release=lambda *_: self.clear_history())
        title = Label(
            text="Historial",
            font_size=dp(38),
            bold=True,
            color=(0, 0, 0, 1),
            halign="center",
            valign="middle",
        )
        title.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        top_row.add_widget(Widget(size_hint_x=0.2))
        top_row.add_widget(title)
        top_row.add_widget(clear_history_btn)
        root.add_widget(top_row)

        history_box = RoundedPanel(
            orientation="vertical",
            bg_color=(1, 1, 1, 1),
            radius=dp(20),
            padding=(dp(12), dp(12), dp(12), dp(12)),
            spacing=dp(8),
        )
        history_box.add_widget(
            Label(
                text="Historial",
                size_hint_y=None,
                height=dp(36),
                font_size=dp(24),
                bold=True,
                color=(0, 0, 0, 1),
            )
        )
        self.history_container = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.history_container.bind(minimum_height=self.history_container.setter("height"))
        history_scroll = ScrollView(do_scroll_x=False, bar_width=dp(8))
        history_scroll.add_widget(self.history_container)
        history_box.add_widget(history_scroll)
        root.add_widget(history_box)

        back_btn = Button(
            text="regresar",
            size_hint_y=None,
            height=dp(54),
            background_normal="",
            background_down="",
            background_color=(0.85, 0, 0, 1),
            color=(0, 0, 0, 1),
            bold=True,
            font_size=dp(30),
        )
        back_btn.bind(on_release=lambda *_: self.go_back())
        root.add_widget(back_btn)
        self.add_widget(root)

    def on_pre_enter(self):
        self.refresh_history()

    def refresh_history(self):
        self.history_container.clear_widgets()
        app = App.get_running_app()
        if not app.signal_history:
            self.history_container.add_widget(
                Label(
                    text="Aun no hay registros de fecha y hora",
                    size_hint_y=None,
                    height=dp(40),
                    color=(0.2, 0.2, 0.2, 1),
                )
            )
            return

        for entry in app.signal_history:
            row = RoundedPanel(
                orientation="horizontal",
                bg_color=(0.95, 0.95, 0.95, 1),
                radius=dp(12),
                size_hint_y=None,
                height=dp(42),
                padding=(dp(10), dp(8), dp(10), dp(8)),
            )
            row_label = Label(
                text=entry,
                color=(0, 0, 0, 1),
                halign="left",
                valign="middle",
            )
            row_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            row.add_widget(row_label)
            self.history_container.add_widget(row)

    def clear_history(self):
        app = App.get_running_app()
        app.signal_history = []
        app.save_history()
        self.refresh_history()

    def go_back(self):
        self.manager.current = "welcome"


class BluetoothScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_ui()

    def _build_ui(self):
        root = RoundedPanel(
            orientation="vertical",
            bg_color=(0 / 255, 203 / 255, 123 / 255, 1),
            padding=(dp(20), dp(16), dp(20), dp(16)),
            spacing=dp(12),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(66), spacing=dp(12))
        title = Label(
            text="Conectar dispositivo",
            font_size=dp(34),
            bold=True,
            color=(0, 0, 0, 1),
            halign="center",
            valign="middle",
        )
        title.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        top_row.add_widget(Widget(size_hint_x=0.2))
        top_row.add_widget(title)
        top_row.add_widget(Widget(size_hint_x=0.2))
        root.add_widget(top_row)

        devices_box = RoundedPanel(
            orientation="vertical",
            bg_color=(1, 1, 1, 1),
            radius=dp(20),
            padding=(dp(12), dp(12), dp(12), dp(12)),
            spacing=dp(8),
        )
        devices_box.add_widget(
            Label(
                text="Conexiones Bluetooth",
                size_hint_y=None,
                height=dp(36),
                font_size=dp(24),
                bold=True,
                color=(0, 0, 0, 1),
            )
        )
        self.devices_container = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.devices_container.bind(minimum_height=self.devices_container.setter("height"))
        devices_scroll = ScrollView(do_scroll_x=False, bar_width=dp(8))
        devices_scroll.add_widget(self.devices_container)
        devices_box.add_widget(devices_scroll)
        root.add_widget(devices_box)

        self.message_label = Label(
            text="",
            size_hint_y=None,
            height=dp(22),
            color=(0.1, 0.35, 0.1, 1),
            font_size=dp(14),
        )
        root.add_widget(self.message_label)

        wifi_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        self.wifi_ip_input = TextInput(
            text="192.168.4.1",
            multiline=False,
            hint_text="IP ESP32 (AP)",
            background_normal="",
            background_active="",
            background_color=(1, 1, 1, 1),
            foreground_color=(0, 0, 0, 1),
            padding=(dp(10), dp(10), dp(10), dp(10)),
        )
        wifi_connect_btn = Button(
            text="Conectar WiFi",
            size_hint_x=None,
            width=dp(160),
            background_normal="",
            background_down="",
            background_color=(0.12, 0.4, 0.88, 1),
            color=(1, 1, 1, 1),
            bold=True,
        )
        wifi_disconnect_btn = Button(
            text="Desconectar WiFi",
            size_hint_x=None,
            width=dp(180),
            background_normal="",
            background_down="",
            background_color=(0.6, 0.2, 0.2, 1),
            color=(1, 1, 1, 1),
            bold=True,
        )
        wifi_connect_btn.bind(on_release=lambda *_: self.connect_wifi_device())
        wifi_disconnect_btn.bind(on_release=lambda *_: self.disconnect_wifi_device())
        wifi_row.add_widget(self.wifi_ip_input)
        wifi_row.add_widget(wifi_connect_btn)
        wifi_row.add_widget(wifi_disconnect_btn)
        root.add_widget(wifi_row)

        scan_btn = Button(
            text="buscar dispositivos",
            size_hint_y=None,
            height=dp(48),
            background_normal="",
            background_down="",
            background_color=(0.35, 0.35, 0.35, 1),
            color=(1, 1, 1, 1),
            bold=True,
            font_size=dp(20),
        )
        scan_btn.bind(on_release=lambda *_: self.scan_devices())
        root.add_widget(scan_btn)

        simulate_btn = Button(
            text="simular senal",
            size_hint_y=None,
            height=dp(48),
            background_normal="",
            background_down="",
            background_color=(0.18, 0.45, 0.85, 1),
            color=(1, 1, 1, 1),
            bold=True,
            font_size=dp(22),
        )
        simulate_btn.bind(on_release=lambda *_: self.simulate_signal())
        root.add_widget(simulate_btn)

        back_btn = Button(
            text="regresar",
            size_hint_y=None,
            height=dp(54),
            background_normal="",
            background_down="",
            background_color=(0.85, 0, 0, 1),
            color=(0, 0, 0, 1),
            bold=True,
            font_size=dp(30),
        )
        back_btn.bind(on_release=lambda *_: self.go_back())
        root.add_widget(back_btn)
        self.add_widget(root)

    def on_pre_enter(self):
        self.scan_devices()
        self.refresh_devices()

    def scan_devices(self):
        app = App.get_running_app()
        self.message_label.text = app.discover_bluetooth_devices()
        self.refresh_devices()

    def refresh_devices(self):
        self.devices_container.clear_widgets()
        app = App.get_running_app()
        if not app.bluetooth_devices:
            self.devices_container.add_widget(
                Label(
                    text="No se encontraron dispositivos",
                    size_hint_y=None,
                    height=dp(40),
                    color=(0.2, 0.2, 0.2, 1),
                )
            )
            return

        for index, device in enumerate(app.bluetooth_devices):
            row = RoundedPanel(
                orientation="horizontal",
                bg_color=(0.95, 0.95, 0.95, 1),
                radius=dp(12),
                size_hint_y=None,
                height=dp(46),
                padding=(dp(10), dp(8), dp(10), dp(8)),
                spacing=dp(8),
            )
            name_label = Label(
                text=f"{device['name']} ({device['address']})",
                color=(0, 0, 0, 1),
                halign="left",
                valign="middle",
            )
            name_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            connect_btn = Button(
                text="Conectado" if device.get("connected") else "Conectar",
                size_hint_x=None,
                width=dp(120),
                background_normal="",
                background_down="",
                background_color=(0.1, 0.55, 0.2, 1) if device.get("connected") else (0.15, 0.35, 0.83, 1),
                color=(1, 1, 1, 1),
                bold=True,
            )
            connect_btn.bind(on_release=lambda _, idx=index: self.toggle_connection(idx))
            row.add_widget(name_label)
            row.add_widget(connect_btn)
            self.devices_container.add_widget(row)

    def toggle_connection(self, index):
        app = App.get_running_app()
        if index < 0 or index >= len(app.bluetooth_devices):
            return
        device = app.bluetooth_devices[index]
        if device.get("connected"):
            ok, msg = app.disconnect_bluetooth_device(index)
        else:
            ok, msg = app.connect_bluetooth_device(index)
        self.message_label.text = msg
        self.refresh_devices()

    def simulate_signal(self):
        app = App.get_running_app()
        connected_devices = [d for d in app.bluetooth_devices if d.get("connected")]
        if not connected_devices:
            self.message_label.text = "Conecte al menos un dispositivo primero"
            return
        device = connected_devices[0]
        app.handle_arduino_signal(f"STOP|{device['name']}|40|0")
        self.message_label.text = "Senal simulada recibida y guardada en historial"

    def connect_wifi_device(self):
        app = App.get_running_app()
        ip = self.wifi_ip_input.text.strip() or "192.168.4.1"
        ok, msg = app.start_wifi_listener(ip)
        self.message_label.text = msg

    def disconnect_wifi_device(self):
        app = App.get_running_app()
        app.stop_wifi_listener()
        self.message_label.text = "WiFi desconectado"

    def go_back(self):
        self.manager.current = "welcome"


class MyApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_name = ""
        self.remember_me = False
        self.contacts = []
        self.signal_history = []
        self.bluetooth_devices = [
            {"name": "Prueba", "address": "PRUEBA-UUID", "connected": False, "transport": "ble"},
        ]
        self.bluetooth_stop_events = {}
        self.bluetooth_threads = {}
        self.bluetooth_status_queue = queue.Queue()
        self.bluetooth_line_buffers = {}
        self.serial_line_buffers = {}
        self.serial_connections = {}
        self.signal_inbox = queue.Queue()
        self.pending_signal_entries = []
        self.active_signal_entry = None
        self.signal_popup = None
        self.signal_countdown_event = None
        self.signal_countdown_value = 0
        self.signal_countdown_label = None
        self.ble_notify_char_uuid = "abcd1234-5678-1234-5678-1234567890ab"
        self.last_received_payload = ""
        self.android_ble_ready = False
        self.android_ble_scanning = False
        self.android_bluetooth_adapter = None
        self.android_ble_scanner = None
        self.android_scan_callback = None
        self.android_gatt_callback = None
        self.android_gatt = None
        self.wifi_device_ip = ""
        self.wifi_listener_thread = None
        self.wifi_stop_event = threading.Event()
        self.wifi_last_payload = ""
        self.wifi_last_payload_ts = 0.0
        self.wifi_poll_interval = 0.25
        self.wifi_last_error_log_ts = 0.0
        self.store = JsonStore("user_data.json")

    def start_wifi_listener(self, ip_address):
        ip = (ip_address or "").strip()
        if not ip:
            return False, "IP invalida"
        if self.wifi_listener_thread is not None and self.wifi_listener_thread.is_alive():
            return True, f"WiFi ya conectado a {self.wifi_device_ip}"

        self.wifi_device_ip = ip
        self.wifi_stop_event.clear()
        self.wifi_last_payload = ""
        self.wifi_last_payload_ts = 0.0
        self.wifi_last_error_log_ts = 0.0
        self.wifi_listener_thread = threading.Thread(target=self._wifi_listener_worker, daemon=True)
        self.wifi_listener_thread.start()
        self.bluetooth_status_queue.put(("connected", "WIFI", f"Conectado por WiFi a {ip}", "WiFi ESP32"))
        return True, f"Conectado por WiFi a {ip}"

    def stop_wifi_listener(self):
        self.wifi_stop_event.set()
        if self.wifi_listener_thread is not None and self.wifi_listener_thread.is_alive():
            self.wifi_listener_thread.join(timeout=1.0)
        self.wifi_listener_thread = None
        self.wifi_device_ip = ""

    def _wifi_listener_worker(self):
        while not self.wifi_stop_event.is_set():
            if not self.wifi_device_ip:
                time.sleep(0.5)
                continue
            try:
                url = f"http://{self.wifi_device_ip}/event"
                with urlopen(url, timeout=2.0) as response:
                    payload = response.read().decode("utf-8", errors="ignore").strip()
                now = time.time()
                is_duplicate_too_soon = payload == self.wifi_last_payload and (now - self.wifi_last_payload_ts) < 0.8
                if payload and payload not in ("NO_EVENT", "OK") and not is_duplicate_too_soon:
                    self.wifi_last_payload = payload
                    self.wifi_last_payload_ts = now
                    try:
                        parsed = json.loads(payload)
                        event_text = parsed.get("event", "")
                        location = parsed.get("location", "")
                        if event_text:
                            self.signal_inbox.put(event_text)
                        if location:
                            self.signal_inbox.put(location)
                    except Exception:
                        for line in payload.splitlines():
                            line = line.strip()
                            if line:
                                self.signal_inbox.put(line)
            except URLError:
                now = time.time()
                if now - self.wifi_last_error_log_ts > 5:
                    self.wifi_last_error_log_ts = now
                    self.bluetooth_status_queue.put(
                        ("error", "WIFI", f"No se pudo consultar http://{self.wifi_device_ip}/event", "WiFi ESP32")
                    )
            except Exception as exc:
                self.bluetooth_status_queue.put(("error", "WIFI", f"Error WiFi: {exc}", "WiFi ESP32"))
            time.sleep(self.wifi_poll_interval)

    def _android_prepare_ble(self):
        if not IS_ANDROID or self.android_ble_ready:
            return self.android_ble_ready
        if autoclass is None:
            return False
        try:
            if request_permissions is not None and Permission is not None:
                request_permissions(
                    [
                        Permission.BLUETOOTH,
                        Permission.BLUETOOTH_ADMIN,
                        Permission.ACCESS_FINE_LOCATION,
                        Permission.BLUETOOTH_SCAN,
                        Permission.BLUETOOTH_CONNECT,
                    ]
                )
        except Exception:
            pass

        try:
            BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
            self.android_bluetooth_adapter = BluetoothAdapter.getDefaultAdapter()
            if self.android_bluetooth_adapter is None:
                return False
            self.android_ble_scanner = self.android_bluetooth_adapter.getBluetoothLeScanner()
            self.android_scan_callback = AndroidScanCallback()
            self.android_gatt_callback = AndroidGattCallback()
            self.android_ble_ready = self.android_ble_scanner is not None
            return self.android_ble_ready
        except Exception:
            return False

    def _android_stop_scan(self, *_):
        if not IS_ANDROID or not self.android_ble_scanning:
            return
        try:
            if self.android_ble_scanner is not None and self.android_scan_callback is not None:
                self.android_ble_scanner.stopScan(self.android_scan_callback)
        except Exception:
            pass
        self.android_ble_scanning = False

    def _android_start_scan(self):
        if not self._android_prepare_ble():
            return "BLE Android no disponible"
        self.bluetooth_devices = []
        try:
            self.android_ble_scanner.startScan(self.android_scan_callback)
            self.android_ble_scanning = True
            Clock.schedule_once(self._android_stop_scan, 6.0)
            return "Escaneando BLE en Android..."
        except Exception as exc:
            return f"Error al escanear BLE Android: {exc}"

    def _android_handle_scan_result(self, result):
        try:
            device = result.getDevice()
            if device is None:
                return
            name = device.getName() or "Dispositivo BLE"
            address = (device.getAddress() or "").upper()
            if not address:
                return
            for item in self.bluetooth_devices:
                if item.get("address") == address:
                    return
            self.bluetooth_devices.append(
                {"name": name, "address": address, "connected": False, "transport": "ble"}
            )
        except Exception:
            return

    def _android_connect_ble(self, device):
        if not self._android_prepare_ble():
            return False, "BLE Android no disponible"
        address = (device.get("address", "") or "").upper()
        if not address:
            return False, "Direccion BLE invalida"
        try:
            if self.android_bluetooth_adapter is None:
                return False, "Adaptador BLE Android no disponible"
            remote_device = self.android_bluetooth_adapter.getRemoteDevice(address)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            try:
                BluetoothDevice = autoclass("android.bluetooth.BluetoothDevice")
                self.android_gatt = remote_device.connectGatt(
                    activity, False, self.android_gatt_callback, BluetoothDevice.TRANSPORT_LE
                )
            except Exception:
                self.android_gatt = remote_device.connectGatt(activity, False, self.android_gatt_callback)
            return True, f"Conectando a {device.get('name', 'BLE')}..."
        except Exception as exc:
            return False, f"Error al conectar BLE Android: {exc}"

    def _android_disconnect_ble(self):
        try:
            if self.android_gatt is not None:
                self.android_gatt.disconnect()
                self.android_gatt.close()
        except Exception:
            pass
        self.android_gatt = None

    def _android_on_connection_state_change(self, gatt, status, new_state):
        if not IS_ANDROID:
            return
        try:
            BluetoothProfile = autoclass("android.bluetooth.BluetoothProfile")
            address = (gatt.getDevice().getAddress() or "").upper()
            name = gatt.getDevice().getName() or "Dispositivo BLE"
            if int(status) != 0:
                self.bluetooth_status_queue.put(("error", address, f"Error BLE ({status}) en {name}", name))
            if new_state == BluetoothProfile.STATE_CONNECTED:
                self.bluetooth_status_queue.put(("connected", address, f"{name} conectado", name))
                gatt.discoverServices()
            elif new_state == BluetoothProfile.STATE_DISCONNECTED:
                self.bluetooth_status_queue.put(("disconnected", address, f"{name} desconectado", name))
        except Exception:
            return

    def _android_on_services_discovered(self, gatt, status):
        if not IS_ANDROID:
            return
        try:
            service_uuid = autoclass("java.util.UUID").fromString("12345678-1234-1234-1234-1234567890ab")
            char_uuid = autoclass("java.util.UUID").fromString(self.ble_notify_char_uuid)
            descriptor_uuid = autoclass("java.util.UUID").fromString("00002902-0000-1000-8000-00805f9b34fb")
            service = gatt.getService(service_uuid)
            if service is None:
                self.bluetooth_status_queue.put(("error", "ANDROID", "Servicio BLE no encontrado", "Android BLE"))
                return
            characteristic = service.getCharacteristic(char_uuid)
            if characteristic is None:
                self.bluetooth_status_queue.put(("error", "ANDROID", "Caracteristica BLE no encontrada", "Android BLE"))
                return
            gatt.setCharacteristicNotification(characteristic, True)
            descriptor = characteristic.getDescriptor(descriptor_uuid)
            if descriptor is not None:
                BluetoothGattDescriptor = autoclass("android.bluetooth.BluetoothGattDescriptor")
                descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                gatt.writeDescriptor(descriptor)
        except Exception as exc:
            self.bluetooth_status_queue.put(("error", "ANDROID", f"Error configurando notify: {exc}", "Android BLE"))

    def _android_on_characteristic_changed(self, characteristic, value=None):
        if not IS_ANDROID:
            return
        try:
            raw_value = value if value is not None else characteristic.getValue()
            text = bytes(raw_value).decode("utf-8", errors="ignore")
            if text:
                self.signal_inbox.put(text.strip())
        except Exception:
            return

    def save_contacts(self):
        self.store.put("contacts", items=self.contacts)

    def save_history(self):
        self.store.put("history", items=self.signal_history)

    def add_history_entry(self, message, timestamp=None):
        ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.signal_history.insert(0, f"{ts} - {message}")
        self.save_history()

    def queue_signal_confirmation(self, message):
        self.pending_signal_entries.append(message)
        if self.active_signal_entry is None and self.signal_popup is None:
            self._show_next_signal_popup()

    def _show_next_signal_popup(self):
        if not self.pending_signal_entries:
            return
        self.active_signal_entry = self.pending_signal_entries.pop(0)
        self.signal_countdown_value = 15

        content = BoxLayout(orientation="vertical", spacing=dp(12), padding=(dp(14), dp(14), dp(14), dp(14)))
        content.add_widget(
            Label(
                text="Se detecto un freno brusco, enviar sms?",
                color=(0, 0, 0, 1),
                halign="center",
                valign="middle",
            )
        )
        self.signal_countdown_label = Label(
            text=f"Confirmacion automatica en {self.signal_countdown_value}s",
            color=(0.25, 0.25, 0.25, 1),
            size_hint_y=None,
            height=dp(28),
        )
        content.add_widget(self.signal_countdown_label)

        buttons_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(10))
        yes_btn = Button(
            text="Si",
            background_normal="",
            background_down="",
            background_color=(0.1, 0.55, 0.2, 1),
            color=(1, 1, 1, 1),
            bold=True,
        )
        no_btn = Button(
            text="No",
            background_normal="",
            background_down="",
            background_color=(0.85, 0.1, 0.1, 1),
            color=(1, 1, 1, 1),
            bold=True,
        )
        yes_btn.bind(on_release=lambda *_: self._resolve_signal_confirmation(True))
        no_btn.bind(on_release=lambda *_: self._resolve_signal_confirmation(False))
        buttons_row.add_widget(yes_btn)
        buttons_row.add_widget(no_btn)
        content.add_widget(buttons_row)

        self.signal_popup = Popup(
            title="Confirmacion",
            content=content,
            size_hint=(None, None),
            size=(dp(460), dp(250)),
            auto_dismiss=False,
        )
        self.signal_popup.open()
        self.signal_countdown_event = Clock.schedule_interval(self._signal_countdown_tick, 1.0)

    def _signal_countdown_tick(self, _dt):
        self.signal_countdown_value -= 1
        if self.signal_countdown_label:
            self.signal_countdown_label.text = f"Confirmacion automatica en {self.signal_countdown_value}s"
        if self.signal_countdown_value <= 0:
            self._resolve_signal_confirmation(True)
            return False
        return True

    def _resolve_signal_confirmation(self, confirmed):
        if self.signal_countdown_event is not None:
            self.signal_countdown_event.cancel()
            self.signal_countdown_event = None

        if confirmed and self.active_signal_entry:
            self.add_history_entry(self.active_signal_entry)

        if self.signal_popup is not None:
            self.signal_popup.dismiss()
            self.signal_popup = None

        self.active_signal_entry = None
        self.signal_countdown_label = None
        self._show_next_signal_popup()

    def handle_arduino_signal(self, payload):
        """
        Supported signal examples:
        - STOP|Sensor Puerta|40|0
        - CHOQUE DETECTADO
        - https://maps.app.goo.gl/...
        """
        text = (payload or "").strip()
        if not text:
            return
        self.last_received_payload = text

        upper_text = text.upper()
        if "G TOTAL" in upper_text:
            # Telemetry lines from ESP32 are informative and should not trigger alerts.
            return

        if "CHOQUE DETECTADO" in upper_text:
            self.queue_signal_confirmation("Frenado/choque brusco detectado por ESP32")
            return

        if text.startswith("http://") or text.startswith("https://"):
            self.add_history_entry(f"Ubicacion reportada: {text}")
            return

        parts = [part.strip() for part in text.split("|")]
        if not parts:
            return
        signal_type = parts[0].upper()
        if signal_type == "STOP":
            sensor_name = parts[1] if len(parts) > 1 and parts[1] else "Sensor desconocido"
            speed_before = parts[2] if len(parts) > 2 and parts[2] else "?"
            speed_after = parts[3] if len(parts) > 3 and parts[3] else "?"
            self.queue_signal_confirmation(
                f"Frenado brusco detectado ({sensor_name}) - velocidad {speed_before} a {speed_after}"
            )

    def discover_bluetooth_devices(self):
        if IS_ANDROID:
            return self._android_start_scan()

        current_state = {d.get("address"): d.get("connected", False) for d in self.bluetooth_devices}
        discovered = []
        ble_count = 0
        serial_count = 0

        if BleakScanner is not None:
            try:
                results = asyncio.run(self._discover_ble_devices())
                for device in results:
                    address = getattr(device, "address", "")
                    name = getattr(device, "name", None) or "Dispositivo BLE"
                    discovered.append(
                        {
                            "name": name,
                            "address": address,
                            "connected": current_state.get(address, False),
                            "transport": "ble",
                        }
                    )
                    ble_count += 1
            except Exception:
                pass

        if list_ports is not None:
            try:
                for port in list_ports.comports():
                    address = port.device
                    label = port.description or "Serial USB"
                    if address.upper() == "COM4":
                        label = "Prueba (USB COM4)"
                    discovered.append(
                        {
                            "name": label,
                            "address": address,
                            "connected": current_state.get(address, False),
                            "transport": "serial",
                        }
                    )
                    serial_count += 1
            except Exception:
                pass

        self.bluetooth_devices = discovered
        if not discovered:
            return "No se encontraron dispositivos BLE/USB"
        return f"{ble_count} BLE y {serial_count} USB detectado(s)"

    async def _discover_ble_devices(self):
        return await BleakScanner.discover(timeout=6.0)

    def connect_bluetooth_device(self, index):
        if index < 0 or index >= len(self.bluetooth_devices):
            return False, "Indice invalido"
        device = self.bluetooth_devices[index]
        address = device.get("address", "")
        transport = device.get("transport", "ble")

        if IS_ANDROID:
            return self._android_connect_ble(device)

        if transport == "serial":
            return self._connect_serial_device(device)

        if BleakClient is None:
            device["connected"] = True
            return True, f"{device['name']} conectado (modo prueba)"

        if address in self.bluetooth_stop_events:
            device["connected"] = True
            return True, f"{device['name']} ya estaba conectado/conectando"

        stop_event = threading.Event()
        self.bluetooth_stop_events[address] = stop_event
        worker = threading.Thread(
            target=self._ble_connection_worker,
            args=(address, device.get("name", "Dispositivo"), stop_event),
            daemon=True,
        )
        self.bluetooth_threads[address] = worker
        worker.start()
        return True, f"Conectando a {device['name']}..."

    def disconnect_bluetooth_device(self, index):
        if index < 0 or index >= len(self.bluetooth_devices):
            return False, "Indice invalido"
        device = self.bluetooth_devices[index]
        address = device.get("address", "")
        transport = device.get("transport", "ble")
        device["connected"] = False

        if IS_ANDROID:
            self._android_disconnect_ble()
            return True, f"{device['name']} desconectado"

        if transport == "serial":
            conn = self.serial_connections.pop(address, None)
            self.serial_line_buffers.pop(address, None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            worker = self.bluetooth_threads.pop(address, None)
            if worker is not None and worker.is_alive():
                worker.join(timeout=1.0)
            return True, f"{device['name']} desconectado"

        stop_event = self.bluetooth_stop_events.pop(address, None)
        if stop_event is not None:
            stop_event.set()
        worker = self.bluetooth_threads.pop(address, None)
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)
        return True, f"{device['name']} desconectado"

    def _ble_connection_worker(self, address, device_name, stop_event):
        # On Windows GUI apps, Bleak may require STA allowance for callbacks.
        if allow_sta is not None:
            try:
                allow_sta()
            except Exception:
                pass
        asyncio.run(self._ble_connection_session(address, device_name, stop_event))

    def _connect_serial_device(self, device):
        if serial is None:
            device["connected"] = True
            return True, f"{device['name']} conectado (modo prueba)"

        address = device.get("address", "")
        if address in self.serial_connections:
            device["connected"] = True
            return True, f"{device['name']} ya estaba conectado"

        try:
            serial_conn = serial.Serial(address, baudrate=9600, timeout=0.2)
            try:
                serial_conn.reset_input_buffer()
                serial_conn.reset_output_buffer()
            except Exception:
                pass
        except Exception as exc:
            device["connected"] = False
            return False, f"Error serial en {address}: {exc}"

        self.serial_connections[address] = serial_conn
        device["connected"] = True
        worker = threading.Thread(
            target=self._serial_reader_worker,
            args=(address, device.get("name", "Serial USB"), serial_conn),
            daemon=True,
        )
        self.bluetooth_threads[address] = worker
        worker.start()
        return True, f"{device['name']} conectado por USB"

    def _serial_reader_worker(self, address, device_name, serial_conn):
        buffer = self.serial_line_buffers.get(address, "")
        while True:
            if self.serial_connections.get(address) is not serial_conn:
                self.serial_line_buffers.pop(address, None)
                return
            try:
                waiting = getattr(serial_conn, "in_waiting", 0) or 0
                chunk = serial_conn.read(waiting if waiting > 0 else 1).decode("utf-8", errors="ignore")
                if not chunk:
                    continue

                buffer += chunk
                payloads, buffer = self._extract_signal_payloads(buffer)
                self.serial_line_buffers[address] = buffer

                for payload in payloads:
                    self.signal_inbox.put(payload)
            except Exception:
                self.serial_line_buffers.pop(address, None)
                self.bluetooth_status_queue.put(("error", address, f"Error leyendo {device_name}", device_name))
                return

    async def _ble_connection_session(self, address, device_name, stop_event):
        client = BleakClient(address)
        notify_uuid = None
        try:
            await client.connect()
            self.bluetooth_status_queue.put(("connected", address, f"{device_name} conectado", device_name))

            notify_uuid = await self._resolve_notify_characteristic(client)
            if notify_uuid is None:
                self.bluetooth_status_queue.put(
                    ("error", address, "No se encontro caracteristica BLE de notificacion", device_name)
                )
                return

            def _on_notify(_sender, data):
                self._process_ble_chunk(address, data)

            await client.start_notify(notify_uuid, _on_notify)
            while not stop_event.is_set():
                await asyncio.sleep(0.2)
            await client.stop_notify(notify_uuid)
        except Exception as exc:
            self.bluetooth_status_queue.put(("error", address, f"Error BLE: {exc}", device_name))
        finally:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception:
                pass
            self.bluetooth_status_queue.put(("disconnected", address, f"{device_name} desconectado", device_name))
            self.bluetooth_stop_events.pop(address, None)
            self.bluetooth_threads.pop(address, None)
            self.bluetooth_line_buffers.pop(address, None)

    async def _resolve_notify_characteristic(self, client):
        target_uuid = (self.ble_notify_char_uuid or "").lower()
        if target_uuid:
            services = await client.get_services()
            for service in services:
                for characteristic in service.characteristics:
                    if characteristic.uuid.lower() == target_uuid and "notify" in characteristic.properties:
                        return characteristic.uuid

        services = await client.get_services()
        for service in services:
            for characteristic in service.characteristics:
                if "notify" in characteristic.properties:
                    return characteristic.uuid
        return None

    def _process_ble_chunk(self, address, data):
        text = data.decode("utf-8", errors="ignore")
        current = self.bluetooth_line_buffers.get(address, "") + text
        payloads, remainder = self._extract_signal_payloads(current)
        self.bluetooth_line_buffers[address] = remainder
        for payload in payloads:
            self.signal_inbox.put(payload)

    def _extract_signal_payloads(self, buffer_text):
        normalized = buffer_text.replace("\r", "\n")
        payloads = []

        lines = normalized.split("\n")
        for line in lines[:-1]:
            payload = line.strip()
            if payload:
                payloads.append(payload)

        remainder = lines[-1]
        # Some boards send STOP frames without newline, so extract complete frames directly.
        matches = list(re.finditer(r"(?i)STOP\|[^|\r\n]*\|[^|\r\n]*\|[^|\r\n]*", remainder))
        if matches:
            for match in matches:
                payloads.append(match.group(0).strip())
            remainder = remainder[matches[-1].end():]

        if len(remainder) > 300:
            remainder = remainder[-300:]
        return payloads, remainder

    def _poll_signal_receiver(self, _dt):
        bluetooth_screen = None
        if self.root:
            try:
                bluetooth_screen = self.root.get_screen("bluetooth")
            except Exception:
                bluetooth_screen = None

        while not self.bluetooth_status_queue.empty():
            status, address, message, device_name = self.bluetooth_status_queue.get_nowait()
            for device in self.bluetooth_devices:
                if (device.get("address") or "").upper() == (address or "").upper():
                    device["connected"] = status == "connected"
                    break
            if bluetooth_screen is not None and status in ("error", "connected", "disconnected"):
                bluetooth_screen.message_label.text = message
        while not self.signal_inbox.empty():
            payload = self.signal_inbox.get_nowait()
            self.handle_arduino_signal(payload)
            if bluetooth_screen is not None:
                bluetooth_screen.message_label.text = f"RX: {self.last_received_payload[:80]}"
        return True

    def build(self):
        Window.clearcolor = (1, 1, 1, 1)
        sm = ScreenManager()
        sm.add_widget(InputScreen(name="input"))
        sm.add_widget(WelcomeScreen(name="welcome"))
        sm.add_widget(HistoryScreen(name="history"))
        sm.add_widget(BluetoothScreen(name="bluetooth"))

        if self.store.exists("settings"):
            self.remember_me = self.store.get("settings").get("remember_me", False)
        if self.store.exists("user"):
            self.user_name = self.store.get("user").get("email", "")
            if self.user_name and self.remember_me:
                sm.current = "welcome"
        if self.store.exists("contacts"):
            self.contacts = self.store.get("contacts").get("items", [])
        if self.store.exists("history"):
            self.signal_history = self.store.get("history").get("items", [])
        Clock.schedule_interval(self._poll_signal_receiver, 1.0)
        return sm


if __name__ == "__main__":
    MyApp().run()
