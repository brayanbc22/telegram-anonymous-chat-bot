# 🎭 Anonymous ChatBot para Telegram

<div align="center">
  
![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Railway](https://img.shields.io/badge/Railway-131415?style=for-the-badge&logo=railway&logoColor=white)

**Conecta con personas de anónimamente a través de este bot de Telegram**

[Características](#características) • 
[Tecnologías](#tecnologías) • 
[Instalación](#instalación) • 
[Despliegue](#despliegue) • 
[Uso](#cómo-usar-el-bot) • 
[Contribuir](#contribuir)

<img src="https://i.imgur.com/yTCGhUB.png" alt="Bot Screenshot" width="300"/>

</div>

## 📝 Descripción

Anonymous ChatBot permite chatear de manera anónima entre sí. El bot actúa como intermediario para mantener la privacidad de los usuarios mientras disfrutan de una conversación con alguien nuevo. ACLARO , NO HACE UN LOG DE LOS CHATS.

## ✨ Características

- 🔒 **Anonimato completo** - El bot actúa como intermediario entre los usuarios
- 🔄 **Emparejamiento aleatorio** - Conecta a los usuarios que estén buscando conversar
- 📱 **Soporte multimedia** - Envío y recepción de mensajes, fotos, stickers, videos y más
- 🛑 **Control de sesión** - Posibilidad de finalizar el chat cuando lo desees
- 🎯 **Interfaz intuitiva** - Uso de botones y comandos simples
- 🎲 **Experiencia conversacional fluida** - No hay límites en la duración de la conversación

## 🛠️ Tecnologías

- [Python 3.13+](https://www.python.org/) - Lenguaje de programación
- [python-telegram-bot](https://python-telegram-bot.org/) - Biblioteca para la API de Telegram
- [Railway](https://railway.app/) - Plataforma de despliegue
- [python-dotenv](https://pypi.org/project/python-dotenv/) - Manejo de variables de entorno

## ⚙️ Instalación

Para ejecutar este bot localmente, sigue estos pasos:

1. Clona este repositorio:
```bash
git clone https://github.com/usuario/telegram-anonymous-chat-bot.git
cd telegram-anonymous-chat-bot
```

2. Crea y activa el entorno virtual:
```bash
python -m venv venv
# En Windows:
venv\Scripts\activate
# En macOS/Linux:
source venv/bin/activate
```

3. Instala las dependencias:
```bash
pip install -r requirements.txt
```

4. Crea un archivo `.env` en la raíz del proyecto:
```
TELEGRAM_TOKEN=tu_token_de_telegram_aquí
```

5. Ejecuta el bot:
```bash
python bot.py
```

## 🚀 Despliegue

### Despliegue en Railway

1. Crea una cuenta en [Railway](https://railway.app/) y conéctala con GitHub
2. Crea un nuevo proyecto y selecciona este repositorio
3. Añade la variable de entorno `TELEGRAM_TOKEN` con tu token de Telegram
4. Railway desplegará automáticamente tu aplicación

Para más detalles, consulta la [guía de despliegue completa](docs/railway-deployment.md).

## 🎮 Cómo usar el bot

1. **Inicia el bot**: Busca tu bot en Telegram por su nombre de usuario y envía `/start`
2. **Lee las instrucciones**: El bot te mostrará un mensaje de bienvenida con las instrucciones básicas
3. **Busca una pareja**: Presiona el botón "Buscar Pareja" o usa el comando `/find`
4. **Espera el emparejamiento**: El bot te notificará cuando encuentre a alguien disponible
5. **¡Inicia la conversación!**: Una vez emparejado, puedes enviar mensajes, fotos, stickers, etc.
6. **Finaliza cuando quieras**: Usa el botón "Finalizar Chat" o el comando `/end` cuando desees terminar

## 📷 Capturas de pantalla

<div align="center">
  <img src="https://i.imgur.com/aFGnfPy.png" alt="Welcome Screen" width="250"/>
  <img src="https://i.imgur.com/Q8iKvOM.png" alt="Searching for Partner" width="250"/>
  <img src="https://i.imgur.com/6Xscwvh.png" alt="Chat Session" width="250"/>
</div>

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! Si tienes ideas para mejorar este bot:

1. Hazme un fork del repositorio
2. Crea una nueva rama (`git checkout -b feature/amazing-feature`)
3. Haz los cambios y el commit (`git commit -m 'Add some amazing feature'`)
4. Hazle push a la rama (`git push origin feature/amazing-feature`)
5. Abre un Pull Request

## 📜 Licencia

Este proyecto está licenciado bajo la Licencia MIT - consulta el archivo [LICENSE](LICENSE) para más detalles.

## 📞 Contacto

Si tienes alguna pregunta o sugerencia, no dudes en abrir un issue o contactarme directamente.
#+53 56205997
---

<div align="center">
  <sub>Construido con ❤️ por <a href="https://github.com/brayanbc22">brayanbc22</a></sub>
</div>
