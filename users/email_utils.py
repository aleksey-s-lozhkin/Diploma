from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.html import strip_tags


def send_verification_email(user, request):
    """Отправляет письмо с подтверждением email"""
    token = user.generate_verification_token()
    verification_url = request.build_absolute_uri(reverse("verify_email", args=[token]))

    subject = "Подтверждение email - Поиск документов"

    # HTML письмо
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                margin: 20px 0;
            }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Подтверждение регистрации</h2>
            <p>Здравствуйте, {user.get_full_name() or user.email}!</p>
            <p>Для подтверждения вашего email и активации аккаунта, пожалуйста, нажмите на кнопку ниже:</p>
            <a href="{verification_url}" class="button">Подтвердить email</a>
            <p>Или скопируйте ссылку в браузер:</p>
            <p>{verification_url}</p>
            <p>Если вы не регистрировались на нашем сайте, просто проигнорируйте это письмо.</p>
            <div class="footer">
                <p>С уважением,<br>Команда Поиск документов</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_message = strip_tags(html_message)

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=False,
    )


def send_password_reset_email(user, request):
    """Отправляет письмо для сброса пароля"""
    token = user.generate_reset_token()
    reset_url = request.build_absolute_uri(reverse("password_reset_confirm", args=[token]))

    subject = "Сброс пароля - Поиск документов"

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #2196F3;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                margin: 20px 0;
            }}
            .warning {{ color: #f44336; font-size: 12px; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Сброс пароля</h2>
            <p>Здравствуйте, {user.get_full_name() or user.email}!</p>
            <p>Вы запросили сброс пароля на нашем сайте. Для установки нового пароля нажмите на кнопку ниже:</p>
            <a href="{reset_url}" class="button">Сбросить пароль</a>
            <p>Или скопируйте ссылку в браузер:</p>
            <p>{reset_url}</p>
            <p class="warning">Ссылка действительна в течение 1 часа.</p>
            <p>Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.</p>
            <div class="footer">
                <p>С уважением,<br>Команда Поиск документов</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_message = strip_tags(html_message)

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=False,
    )
