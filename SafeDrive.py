from kivy.app import App
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget


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

        form_box = BoxLayout(orientation="vertical", spacing=dp(18), size_hint_y=None, height=dp(380))
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

        form_box.add_widget(self.email_input)
        form_box.add_widget(self.password_input)
        form_box.add_widget(self.message_label)
        form_box.add_widget(Widget(size_hint_y=0.2))
        form_box.add_widget(self.login_btn)
        form_box.add_widget(Widget(size_hint_y=0.6))

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
        app.store.put("user", email=email)
        self._set_message("")
        self.manager.current = "welcome"

    def on_pre_enter(self):
        self.email_input.text = ""
        self.password_input.text = ""
        self._set_message("")


class WelcomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=dp(28), spacing=dp(20))
        self.greeting = Label(text="", font_size=dp(30), color=(0.2, 0.2, 0.2, 1))
        back_btn = Button(
            text="Volver",
            size_hint=(None, None),
            width=dp(180),
            height=dp(50),
            background_normal="",
            background_down="",
            background_color=(0 / 255, 98 / 255, 53 / 255, 1),
            color=(1, 1, 1, 1),
        )
        back_btn.bind(on_release=lambda *_: self.go_back())
        layout.add_widget(Widget())
        layout.add_widget(self.greeting)
        layout.add_widget(back_btn)
        layout.add_widget(Widget())
        self.add_widget(layout)

    def on_pre_enter(self):
        app = App.get_running_app()
        email = getattr(app, "user_name", "")
        self.greeting.text = f"Bienvenido, {email}" if email else "Bienvenido"

    def go_back(self):
        self.manager.current = "input"


class MyApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_name = ""
        self.store = JsonStore("user_data.json")

    def build(self):
        Window.clearcolor = (1, 1, 1, 1)
        sm = ScreenManager()
        sm.add_widget(InputScreen(name="input"))
        sm.add_widget(WelcomeScreen(name="welcome"))

        if self.store.exists("user"):
            self.user_name = self.store.get("user").get("email", "")
            if self.user_name:
                sm.current = "welcome"
        return sm


if __name__ == "__main__":
    MyApp().run()
