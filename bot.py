#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import random
import string
import os
from dotenv import load_dotenv

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Almacenamiento de usuarios
waiting_users = []  # Lista de usuarios esperando ser emparejados
active_chats = {}   # Diccionario para mantener los chats activos: {user_id: partner_id}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para iniciar el bot y mostrar la información de bienvenida."""
    user = update.effective_user
    welcome_message = (
        f"👋 ¡Hola {user.first_name}! Bienvenido/a a *Anonymous Chat Bot*.\n\n"
        "Este bot te permite chatear anónimamente con otras personas.\n\n"
        "*Instrucciones:*\n"
        "1️⃣ Presiona el botón 'Buscar Pareja' para comenzar a buscar alguien con quien chatear.\n"
        "2️⃣ Una vez emparejado, podrás enviar mensajes, fotos, stickers y más.\n"
        "3️⃣ Si deseas terminar la conversación, presiona 'Finalizar Chat'.\n\n"
        "🔒 Tu identidad permanecerá anónima durante toda la conversación.\n"
        "💬 ¡Diviértete conociendo nuevas personas!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
        [InlineKeyboardButton("ℹ️ Ayuda", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra información de ayuda."""
    help_message = (
        "*Comandos disponibles:*\n"
        "/start - Iniciar el bot\n"
        "/find - Buscar una pareja para chatear\n"
        "/end - Finalizar la conversación actual\n"
        "/help - Mostrar este mensaje de ayuda\n\n"
        "También puedes usar los botones que aparecen en el chat."
    )
    
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def find_partner_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para buscar pareja."""
    await find_partner(update, context)

async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Función para buscar y emparejar usuarios."""
    user_id = update.effective_user.id
    
    # Verificar si el usuario ya está en un chat activo
    if user_id in active_chats:
        if isinstance(update.callback_query, Update.callback_query.__class__):
            await update.callback_query.answer("Ya estás en una conversación. Finaliza la actual antes de buscar una nueva.")
            return
        await update.message.reply_text("Ya estás en una conversación. Usa /end para finalizar la actual antes de buscar una nueva.")
        return
    
    # Verificar si el usuario ya está esperando
    if user_id in waiting_users:
        if isinstance(update.callback_query, Update.callback_query.__class__):
            await update.callback_query.answer("Ya estás en la lista de espera. Por favor, espera a que alguien se conecte.")
            return
        await update.message.reply_text("Ya estás en la lista de espera. Por favor, espera a que alguien se conecte.")
        return
    
    # Intentar emparejar con algún usuario en espera
    if waiting_users:
        partner_id = waiting_users.pop(0)
        
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        
        # Enviar mensaje a ambos usuarios
        keyboard = [[InlineKeyboardButton("❌ Finalizar Chat", callback_data="end_chat")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 ¡Has sido emparejado! Puedes comenzar a chatear ahora. Tu identidad es anónima.",
            reply_markup=reply_markup
        )
        
        await context.bot.send_message(
            chat_id=partner_id,
            text="🎉 ¡Has sido emparejado! Puedes comenzar a chatear ahora. Tu identidad es anónima.",
            reply_markup=reply_markup
        )
    else:
        # Añadir usuario a la lista de espera
        waiting_users.append(user_id)
        
        keyboard = [[InlineKeyboardButton("❌ Cancelar Búsqueda", callback_data="cancel_search")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.edit_message_text(
                "⏳ Esperando a que alguien se conecte...\n\nPuedes cancelar la búsqueda en cualquier momento.",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "⏳ Esperando a que alguien se conecte...\n\nPuedes cancelar la búsqueda en cualquier momento.",
                reply_markup=reply_markup
            )

async def end_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Finaliza el chat actual."""
    user_id = update.effective_user.id
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # Informar a ambos usuarios
        keyboard = [
            [InlineKeyboardButton("🔍 Buscar Otra Pareja", callback_data="find_partner")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=user_id,
            text="❗ Chat finalizado. La otra persona ha sido notificada.",
            reply_markup=reply_markup
        )
        
        await context.bot.send_message(
            chat_id=partner_id,
            text="❗ Tu pareja ha finalizado el chat.",
            reply_markup=reply_markup
        )
        
        # Eliminar la relación del chat
        del active_chats[user_id]
        del active_chats[partner_id]
    else:
        keyboard = [
            [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "No estás en ninguna conversación actualmente.",
            reply_markup=reply_markup
        )

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancela la búsqueda de pareja."""
    user_id = update.effective_user.id
    
    if user_id in waiting_users:
        waiting_users.remove(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "❌ Búsqueda cancelada. ¿Qué deseas hacer ahora?",
        reply_markup=reply_markup
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el menú principal."""
    keyboard = [
        [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
        [InlineKeyboardButton("ℹ️ Ayuda", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "🏠 *Menú Principal*\n\nSelecciona una opción:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los mensajes enviados por los usuarios."""
    user_id = update.effective_user.id
    
    # Verificar si el usuario está en un chat activo
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # Reenviar el mensaje al compañero
        if update.message.text:
            await context.bot.send_message(chat_id=partner_id, text=update.message.text)
            
        elif update.message.sticker:
            await context.bot.send_sticker(chat_id=partner_id, sticker=update.message.sticker.file_id)
            
        elif update.message.photo:
            await context.bot.send_photo(
                chat_id=partner_id,
                photo=update.message.photo[-1].file_id,
                caption=update.message.caption
            )
            
        elif update.message.voice:
            await context.bot.send_voice(
                chat_id=partner_id,
                voice=update.message.voice.file_id
            )
            
        elif update.message.video:
            await context.bot.send_video(
                chat_id=partner_id,
                video=update.message.video.file_id,
                caption=update.message.caption
            )
            
        elif update.message.animation:
            await context.bot.send_animation(
                chat_id=partner_id,
                animation=update.message.animation.file_id
            )
            
        elif update.message.document:
            await context.bot.send_document(
                chat_id=partner_id,
                document=update.message.document.file_id,
                caption=update.message.caption
            )
            
        elif update.message.audio:
            await context.bot.send_audio(
                chat_id=partner_id,
                audio=update.message.audio.file_id,
                caption=update.message.caption
            )
    else:
        # El usuario no está en un chat activo
        keyboard = [
            [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
            [InlineKeyboardButton("ℹ️ Ayuda", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "No estás en una conversación actualmente. ¿Deseas buscar una pareja para chatear?",
            reply_markup=reply_markup
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las pulsaciones de botones."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "find_partner":
        await find_partner(update, context)
    elif query.data == "end_chat":
        user_id = update.effective_user.id
        if user_id in active_chats:
            partner_id = active_chats[user_id]
            
            # Informar a ambos usuarios
            keyboard = [
                [InlineKeyboardButton("🔍 Buscar Otra Pareja", callback_data="find_partner")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=user_id,
                text="❗ Chat finalizado. La otra persona ha sido notificada.",
                reply_markup=reply_markup
            )
            
            await context.bot.send_message(
                chat_id=partner_id,
                text="❗ Tu pareja ha finalizado el chat.",
                reply_markup=reply_markup
            )
            
            # Eliminar la relación del chat
            del active_chats[user_id]
            del active_chats[partner_id]
    elif query.data == "cancel_search":
        await cancel_search(update, context)
    elif query.data == "main_menu":
        await main_menu(update, context)
    elif query.data == "help":
        help_message = (
            "*Comandos disponibles:*\n"
            "/start - Iniciar el bot\n"
            "/find - Buscar una pareja para chatear\n"
            "/end - Finalizar la conversación actual\n"
            "/help - Mostrar este mensaje de ayuda\n\n"
            "También puedes usar los botones que aparecen en el chat."
        )
        
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_message, parse_mode='Markdown', reply_markup=reply_markup)

def main() -> None:
    """Función principal para iniciar el bot."""
    # Crear la aplicación
    application = Application.builder().token(TOKEN).build()

    # Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("find", find_partner_command))
    application.add_handler(CommandHandler("end", end_chat))
    
    # Callback de botones
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Manejo de mensajes
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    # Iniciar el bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()