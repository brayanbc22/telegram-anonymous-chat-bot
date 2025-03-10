#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import os
import json
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
from data_store import DataStore, format_time_difference, get_gender_emoji, get_gender_name

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "YOUR_TELEGRAM_ID"))  # Tu ID como superadmin

# Estados de conversación
GENDER_SELECTION, WAITING_MATCH, IN_CHAT = range(3)
REPORT_REASON, REPORT_EVIDENCE = range(3, 5)
ADMIN_ADD, ADMIN_REMOVE = range(5, 7)

# Inicializar el almacén de datos
db = DataStore(SUPER_ADMIN_ID)

# Clase Admin Commands integrada desde admin_commands.py
class AdminCommands:
    """Clase que maneja los comandos administrativos del bot."""

    def __init__(self, data_store):
        self.data_store = data_store
        # Store super admin ID for easier access
        self.super_admin_id = SUPER_ADMIN_ID

    def register_handlers(self, dispatcher):
        """Registra todos los manejadores relacionados con comandos administrativos."""
        # Prioridad más alta para comandos administrativos
        dispatcher.add_handler(CommandHandler("admin", self.admin_panel))
        dispatcher.add_handler(CommandHandler("userinfo", self.user_info_command))
        dispatcher.add_handler(CommandHandler("ban", self.ban_user_command))
        dispatcher.add_handler(CommandHandler("unban", self.unban_user_command))
        dispatcher.add_handler(CommandHandler("add_admin", self.add_admin_command))
        dispatcher.add_handler(CommandHandler("remove_admin", self.remove_admin_command))
        
        # Asegurarse de que este CallbackQueryHandler se ejecute antes del general
        # Manejar todos los callbacks que empiezan por admin_ y relacionados con administración
        dispatcher.add_handler(CallbackQueryHandler(self.admin_callback, pattern='^admin_'))
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el panel de administración."""
        user_id = update.effective_user.id
        logger.info(f"Usuario {user_id} intentando acceder al panel de administración")
        
        if not self.data_store.is_admin(user_id):
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer("No tienes permisos de administrador.")
                await update.callback_query.edit_message_text("Lo siento, solo los administradores pueden acceder a este comando.")
            else:
                await update.message.reply_text("Lo siento, solo los administradores pueden acceder a este comando.")

        # Obtener estadísticas para el panel admin
        total_users = self.data_store.stats["total_users"]
        active_chats = len(self.data_store.active_chats) // 2
        pending_reports = sum(1 for r in self.data_store.reports if r.get("status") == "pending")
        
        admin_message = (
            "👑 *Panel de Administrador*\n\n"
            f"👤 Total de usuarios: {total_users}\n"
            f"💬 Conversaciones activas: {active_chats}\n"
            f"🚨 Reportes pendientes: {pending_reports}\n\n"
            "Selecciona una opción:"
        )

        # Crear botones para el panel de administración
        keyboard = [
            [InlineKeyboardButton("📊 Estadísticas", callback_data="admin_stats")],
            [InlineKeyboardButton("👤 Buscar usuario por ID", callback_data="admin_search_user")],
            [InlineKeyboardButton("📝 Ver reportes", callback_data="admin_reports")],
            [InlineKeyboardButton("🚫 Gestionar baneo", callback_data="admin_ban_menu")]
        ]

        if self.data_store.is_super_admin(user_id):
            keyboard.append([InlineKeyboardButton("👑 Gestionar administradores", callback_data="admin_manage_admins")])
        
        keyboard.append([InlineKeyboardButton("🏠 Volver al Menú", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(admin_message, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await update.message.reply_text(admin_message, parse_mode='Markdown', reply_markup=reply_markup)
        
    async def admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja los callbacks del panel de administración."""
        query = update.callback_query
        user_id = query.from_user.id
        
        if not self.data_store.is_admin(user_id):
            await query.answer("No tienes permisos de administrador.", show_alert=True)
            await query.edit_message_text("Acceso denegado.")

        callback_data = query.data
        
        # Panel principal
        if callback_data == "admin_panel":
            await self.admin_panel(update, context)
        
        # Acciones de usuario
        elif callback_data == "admin_search_user":
            await self.admin_search_user(update, context)
            
        # Estadísticas
        elif callback_data == "admin_stats":
            await self.show_admin_stats(update, context)
            
        # Reportes
        elif callback_data == "admin_reports":
            await self.show_reports(update, context)
            
        # Baneos
        elif callback_data == "admin_ban_menu":
            await self.show_ban_menu(update, context)
            
        elif callback_data == "admin_ban_by_id":
            await self.handle_ban_by_id(update, context)

        elif callback_data == "admin_unban_by_id":
            await self.handle_unban_by_id(update, context)

        elif callback_data.startswith("admin_ban_"):
            parts = callback_data.split("_")
            if len(parts) > 2 and parts[-1].isdigit():
                user_id_to_ban = int(parts[-1])
                await self.process_ban(update, context, user_id_to_ban)
            else:
                await query.answer("ID no válido.", show_alert=True)

        elif callback_data.startswith("admin_unban_"):
            parts = callback_data.split("_")
            if len(parts) > 2 and parts[-1].isdigit():
                user_id_to_unban = int(parts[-1])
                await self.process_unban(update, context, user_id_to_unban)
            else:
                await query.answer("ID no válido.", show_alert=True)

        elif callback_data == "admin_add_admin":
            await self.handle_add_admin(update, context)

        elif callback_data == "admin_remove_admin":
            await self.handle_remove_admin(update, context)
            
        # Gestión de administradores
        elif callback_data == "admin_manage_admins":
            await self.show_admin_management(update, context)
            
        # Acción de baneo
        elif callback_data.startswith("admin_ban_"):
            user_id_to_ban = int(callback_data.split("_")[-1])
            await self.process_ban(update, context, user_id_to_ban)
            
        # Acción de desbaneo
        elif callback_data.startswith("admin_unban_"):
            user_id_to_unban = int(callback_data.split("_")[-1])
            await self.process_unban(update, context, user_id_to_unban)
            
        # Ver reportes de usuario
        elif callback_data.startswith("admin_view_reports_"):
            target_user_id = int(callback_data.split("_")[-1])
            await self.show_user_reports(update, context, target_user_id)
            
        # Resolver reporte
        elif callback_data.startswith("admin_resolve_report_"):
            report_id = int(callback_data.split("_")[-1])
            await self.handle_report_action(update, context, report_id, "resolved")
            
        # Descartar reporte
        elif callback_data.startswith("admin_dismiss_report_"):
            report_id = int(callback_data.split("_")[-1])
            await self.handle_report_action(update, context, report_id, "dismissed")
            
        else:
            await query.answer("Función no implementada")
            logger.warning(f"Callback admin no manejado: {callback_data}")
        
        await query.answer()

    async def handle_report_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE, report_id, action):
        """Maneja las acciones sobre reportes (resolver, descartar)."""
        query = update.callback_query
        user_id = query.from_user.id
        
        if report_id >= len(self.data_store.reports):
            await query.edit_message_text("Este reporte ya no existe.")
            return
        
        report = self.data_store.reports[report_id]
        
        if action == "resolved":
            report["status"] = "resolved"
            report["resolved_by"] = user_id
            report["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_msg = "resuelto"
        else:  # dismissed
            report["status"] = "dismissed"
            report["dismissed_by"] = user_id
            report["dismissed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_msg = "descartado"
        
        self.data_store.save_data()
        
        keyboard = [[InlineKeyboardButton("🔙 Volver a Reportes", callback_data="admin_reports")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"El reporte #{report_id} ha sido marcado como {status_msg}.",
            reply_markup=reply_markup
        )

    async def show_admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra estadísticas detalladas para los administradores."""
        query = update.callback_query
        stats = self.data_store.stats
        content_types = stats["content_types"]
        gender_stats = stats["gender_stats"]
        
        stats_message = (
            "📊 *Estadísticas Detalladas*\n\n"
            f"👥 *Usuarios registrados:* {stats['total_users']}\n"
            f"👤 *Usuarios activos (24h):* {stats['daily_active_users']}\n"
            f"💬 *Chats totales:* {stats['total_chats']}\n"
            f"📝 *Mensajes enviados:* {stats['messages_sent']}\n\n"
            f"*Distribución por género:*\n"
        )
        
        total_users = max(1, stats['total_users'])
        for gender, count in gender_stats.items():
            gender_name = get_gender_name(gender)
            emoji = get_gender_emoji(gender)
            percentage = int(count/total_users*100)
            stats_message += f"{emoji} {gender_name}: {count} ({percentage}%)\n"
        
        stats_message += f"\n*Tipos de contenido:*\n"
        stats_message += f"💬 Texto: {content_types['text']}\n"
        stats_message += f"🖼️ Fotos: {content_types['photo']}\n"
        stats_message += f"😎 Stickers: {content_types['sticker']}\n"
        stats_message += f"🎤 Audio/Voz: {content_types['voice'] + content_types['audio']}\n"
        stats_message += f"📹 Videos/GIFs: {content_types['video'] + content_types['animation']}\n"
        stats_message += f"📄 Documentos: {content_types['document']}\n\n"
        
        reports = self.data_store.reports
        stats_message += f"🚨 *Reportes:*\n"
        stats_message += f"- Pendientes: {sum(1 for r in reports if r.get('status') == 'pending')}\n"
        stats_message += f"- Resueltos: {sum(1 for r in reports if r.get('status') == 'resolved')}\n"
        stats_message += f"- Descartados: {sum(1 for r in reports if r.get('status') == 'dismissed')}"
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_message, parse_mode='Markdown', reply_markup=reply_markup)

    async def show_reports(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra los reportes pendientes."""
        query = update.callback_query
        pending_reports = [r for r in self.data_store.reports if r.get("status") == "pending"]
        
        if not pending_reports:
            keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("No hay reportes pendientes de revisión.", reply_markup=reply_markup)
            return ConversationHandler.END
        
        # Mostrar el primer reporte pendiente
        report = pending_reports[0]
        report_id = self.data_store.reports.index(report)
        
        report_text = (
            f"🚨 *Reporte #{report_id}*\n\n"
            f"*De:* Usuario #{report['reporter_id']}\n"
            f"*Contra:* Usuario #{report['reported_id']}\n"
            f"*Fecha:* {report['timestamp']}\n"
            f"*Motivo:* {report['reason']}\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Resolver", callback_data=f"admin_resolve_report_{report_id}"),
                InlineKeyboardButton("❌ Descartar", callback_data=f"admin_dismiss_report_{report_id}")
            ],
            [
                InlineKeyboardButton("🚫 Banear Usuario", callback_data=f"admin_ban_{report['reported_id']}")
            ],
            [InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if report.get("evidence_file_id"):
            try:
                await query.message.delete()
                await context.bot.send_photo(
                    chat_id=query.from_user.id,
                    photo=report["evidence_file_id"],
                    caption=report_text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Error al enviar foto de reporte: {e}")
                await query.edit_message_text(
                    report_text + "\n\n*Evidencia:* Disponible pero no se pudo cargar",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
        else:
            await query.edit_message_text(
                report_text + "\n\n*Evidencia:* No proporcionada",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    async def user_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra información sobre un usuario específico."""
        await try_delete_user_message(update)
        user_id = update.effective_user.id
        
        if not self.data_store.is_admin(user_id):
            await update.message.reply_text("No tienes permisos para usar este comando.")
            return
            
        # Verificar si se proporcionó un ID de usuario
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text(
                "Por favor, proporciona un ID de usuario válido.\n"
                "Ejemplo: /userinfo 123456789"
            )
            return
            
        target_id = int(context.args[0])
        await self.show_user_info(update, context, target_id)

    async def ban_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando para banear a un usuario."""
        await try_delete_user_message(update)
        user_id = update.effective_user.id
        
        if not self.data_store.is_admin(user_id):
            await update.message.reply_text("No tienes permisos para usar este comando.")
            return
            
        # Verificar si se proporcionó un ID de usuario
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text(
                "Por favor, proporciona un ID de usuario válido.\n"
                "Ejemplo: /ban 123456789"
            )
            return
            
        target_id = int(context.args[0])
        
        # Intentar banear al usuario
        if self.data_store.ban_user(target_id):
            # Si el usuario estaba en un chat, finalizarlo
            if target_id in self.data_store.active_chats:
                partner_id = self.data_store.active_chats[target_id]
                self.data_store.end_chat(target_id)
                
                # Notificar a la pareja
                keyboard = [
                    [InlineKeyboardButton("🔍 Buscar Otra Pareja", callback_data="find_partner")],
                    [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=partner_id,
                    text="❗ Tu pareja ha sido desconectada por un administrador.",
                    reply_markup=reply_markup
                )
                
            await update.message.reply_text(f"✅ Usuario #{target_id} ha sido baneado correctamente.")
        else:
            await update.message.reply_text(
                f"❌ No se pudo banear al usuario #{target_id}. Puede ser un administrador o ya está baneado."
            )

    async def unban_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando para desbanear a un usuario."""
        await try_delete_user_message(update)
        user_id = update.effective_user.id
        
        if not self.data_store.is_admin(user_id):
            await update.message.reply_text("No tienes permisos para usar este comando.")
            return
            
        # Verificar si se proporcionó un ID de usuario
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text(
                "Por favor, proporciona un ID de usuario válido.\n"
                "Ejemplo: /unban 123456789"
            )
            return
            
        target_id = int(context.args[0])
        
        # Intentar desbanear al usuario
        if self.data_store.unban_user(target_id):
            await update.message.reply_text(f"✅ Usuario #{target_id} ha sido desbaneado correctamente.")
        else:
            await update.message.reply_text(
                f"❌ No se pudo desbanear al usuario #{target_id}. Puede que no esté baneado."
            )

    async def show_user_reports(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
        """Muestra los reportes relacionados con un usuario específico."""
        query = update.callback_query
        user_reports = [r for r in self.data_store.reports if r["reported_id"] == target_user_id]
        
        if not user_reports:
            keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"El usuario #{target_user_id} no tiene reportes.", reply_markup=reply_markup)
            return
            
        # Mostrar resumen de reportes
        reports_text = f"🚨 *Reportes del Usuario #{target_user_id}*\n\n"
        
        for i, report in enumerate(user_reports):
            status = report.get("status", "pending")
            status_emoji = "⏳" if status == "pending" else "✅" if status == "resolved" else "❌"
            reports_text += f"{status_emoji} Reporte #{i}: {report['reason'][:30]}...\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(reports_text, parse_mode='Markdown', reply_markup=reply_markup)

    async def process_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id_to_ban):
        """Procesa la acción de banear a un usuario desde el panel admin."""
        # Determinar si la actualización viene de un callback o un mensaje de texto
        is_callback = update.callback_query is not None
        
        if self.data_store.ban_user(user_id_to_ban):
            # Si el usuario estaba en un chat, finalizarlo
            if user_id_to_ban in self.data_store.active_chats:
                partner_id = self.data_store.active_chats[user_id_to_ban]
                self.data_store.end_chat(user_id_to_ban)
                
                # Notificar a la pareja
                keyboard = [
                    [InlineKeyboardButton("🔍 Buscar Otra Pareja", callback_data="find_partner")],
                    [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=partner_id,
                    text="❗ Tu pareja ha sido desconectada por un administrador.",
                    reply_markup=reply_markup
                )
            
            keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            success_text = f"✅ Usuario #{user_id_to_ban} ha sido baneado correctamente."
            if is_callback:
                await update.callback_query.edit_message_text(success_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(success_text, reply_markup=reply_markup)
        else:
            keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            error_text = f"❌ No se pudo banear al usuario #{user_id_to_ban}. Puede ser un administrador o ya está baneado."
            if is_callback:
                await update.callback_query.edit_message_text(error_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_text, reply_markup=reply_markup)

    async def process_unban(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id_to_unban):
        """Procesa la acción de desbanear a un usuario desde el panel admin."""
        # Determinar si la actualización viene de un callback o un mensaje de texto
        is_callback = update.callback_query is not None
        
        if self.data_store.unban_user(user_id_to_unban):
            keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            success_text = f"✅ Usuario #{user_id_to_unban} ha sido desbaneado correctamente."
            if is_callback:
                await update.callback_query.edit_message_text(success_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(success_text, reply_markup=reply_markup)
        else:
            keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            error_text = f"❌ No se pudo desbanear al usuario #{user_id_to_unban}. Puede que no esté baneado."
            if is_callback:
                await update.callback_query.edit_message_text(error_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_text, reply_markup=reply_markup)

    async def show_ban_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el menú de gestión de baneos."""
        query = update.callback_query
        
        keyboard = [
            [InlineKeyboardButton("🚫 Banear Usuario por ID", callback_data="admin_ban_by_id")],
            [InlineKeyboardButton("✅ Desbanear Usuario por ID", callback_data="admin_unban_by_id")],
            [InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🚫 *Gestión de Baneos*\n\n"
            "Selecciona una acción:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def show_admin_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el menú de gestión de administradores."""
        query = update.callback_query
        user_id = query.from_user.id
        
        if not self.data_store.is_super_admin(user_id):
            await query.answer("Solo el superadministrador puede acceder a esta función.", show_alert=True)
            await self.admin_panel(update, context)
            return
            
        admin_list = "\n".join([f"• Admin #{admin_id}" for admin_id in self.data_store.admins 
                            if admin_id != self.super_admin_id])
        if not admin_list:
            admin_list = "No hay administradores adicionales."
            
        admin_message = (
            "👑 *Gestión de Administradores*\n\n"
            f"*Superadmin:* #{self.super_admin_id}\n\n"
            f"*Administradores actuales:*\n{admin_list}\n\n"
            "¿Qué acción deseas realizar?"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Añadir Admin", callback_data="admin_add_admin")],
            [InlineKeyboardButton("➖ Eliminar Admin", callback_data="admin_remove_admin")],
            [InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(admin_message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def admin_search_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Solicita un ID de usuario para buscar información."""
        query = update.callback_query
        
        await query.edit_message_text(
            "🔍 *Buscar Usuario por ID*\n\n"
            "Por favor, ingresa el ID del usuario que deseas buscar:",
            parse_mode='Markdown'
        )
        
        # Store state to identify upcoming messages as user ID inputs
        context.user_data['expecting_user_id'] = True
        
        # Add a message handler for this specific user
        application = context.application
        user_id = update.effective_user.id
        
        # Initialize temp_handlers dict if needed
        if not hasattr(context.application, 'temp_handlers'):
            context.application.temp_handlers = {}
        
        # Register a temporary handler for this specific user
        async def user_id_input_handler(update_inner: Update, context_inner: ContextTypes.DEFAULT_TYPE):
            if update_inner.effective_user.id != user_id:
                return
                
            if 'expecting_user_id' not in context_inner.user_data:
                return
                
            del context_inner.user_data['expecting_user_id']
            
            # Remove this temporary handler
            if user_id in context_inner.application.temp_handlers:
                handler_to_remove = context_inner.application.temp_handlers[user_id]
                application.remove_handler(handler_to_remove)
                del context_inner.application.temp_handlers[user_id]
                    
            # Process the user ID
            text = update_inner.message.text.strip()
            if text.isdigit():
                target_id = int(text)
                await self.show_user_info(update_inner, context_inner, target_id)
            else:
                keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update_inner.message.reply_text(
                    "❌ Por favor, introduce un ID de usuario válido (número).",
                    reply_markup=reply_markup
                )
        
        # Create handler
        handler = MessageHandler(filters.TEXT & ~filters.COMMAND, user_id_input_handler)
        
        # Store our handler for later removal
        context.application.temp_handlers[user_id] = handler
        
        # Add the handler (using proper API method)
        application.add_handler(handler, group=0)
    
    async def show_user_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int):
        """Muestra información detallada sobre un usuario específico."""
        # Buscar información del usuario
        if target_id in self.data_store.users:
            user_data = self.data_store.users[target_id]
            
            # Formatear la información del usuario
            gender_emoji = get_gender_emoji(user_data.get("gender", "unknown"))
            gender_name = get_gender_name(user_data.get("gender", "unknown"))
            
            last_active = "Nunca" if not user_data.get("last_active") else datetime.fromtimestamp(
                user_data["last_active"]).strftime("%Y-%m-%d %H:%M:%S")
                
            reports_count = sum(1 for r in self.data_store.reports if r["reported_id"] == target_id)
            
            is_admin = "✅ Sí" if self.data_store.is_admin(target_id) else "❌ No"
            is_super = "✅ Sí" if self.data_store.is_super_admin(target_id) else "❌ No"
            is_banned = "✅ Sí" if user_data.get("banned", False) else "❌ No"
            
            user_info = (
                f"📊 *Información del Usuario #{target_id}*\n\n"
                f"👤 *Género:* {gender_emoji} {gender_name}\n"
                f"⏱️ *Última actividad:* {last_active}\n"
                f"🚨 *Reportes recibidos:* {reports_count}\n"
                f"👑 *Es admin:* {is_admin}\n"
                f"⭐ *Es super admin:* {is_super}\n"
                f"🚫 *Está baneado:* {is_banned}\n"
            )
            
            # Crear botones para acciones administrativas
            keyboard = []
            
            if not self.data_store.is_admin(target_id):
                if user_data.get("banned", False):
                    keyboard.append([InlineKeyboardButton("✅ Desbanear Usuario", callback_data=f"admin_unban_{target_id}")])
                else:
                    keyboard.append([InlineKeyboardButton("🚫 Banear Usuario", callback_data=f"admin_ban_{target_id}")])
                
            keyboard.append([InlineKeyboardButton("🔍 Ver Reportes del Usuario", callback_data=f"admin_view_reports_{target_id}")])
            keyboard.append([InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Handle both message and callback query responses
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(user_info, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                await update.message.reply_text(user_info, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            text = f"No se encontró información para el usuario con ID {target_id}."
            keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)

    async def handle_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Solicita el ID del usuario a convertir en administrador."""
        query = update.callback_query
        await query.edit_message_text(
            "👑 *Añadir Administrador*\n\n"
            "Introduce el ID del usuario:",
            parse_mode='Markdown'
        )
        application = context.application
        invoker_id = query.from_user.id

        if not hasattr(application, 'temp_handlers'):
            application.temp_handlers = {}

        async def user_id_input_handler(update_inner: Update, context_inner: ContextTypes.DEFAULT_TYPE):
            if update_inner.effective_user.id != invoker_id:
                return
            handler_tmp = application.temp_handlers.pop(invoker_id, None)
            if handler_tmp:
                application.remove_handler(handler_tmp)
            text = update_inner.message.text.strip()
            if text.isdigit():
                new_admin_id = int(text)
                if new_admin_id == self.super_admin_id:
                    await update_inner.message.reply_text("❌ El superadministrador ya tiene permisos.")
                    return
                if self.data_store.add_admin(new_admin_id):
                    await update_inner.message.reply_text(f"✅ Usuario #{new_admin_id} ahora es administrador.")
                else:
                    await update_inner.message.reply_text(f"❌ El usuario #{new_admin_id} ya era administrador.")
            else:
                await update_inner.message.reply_text("❌ ID inválido. Operación cancelada.")

        handler = MessageHandler(filters.TEXT & ~filters.COMMAND, user_id_input_handler)
        application.temp_handlers[invoker_id] = handler
        application.add_handler(handler, group=0)

    async def handle_remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Solicita el ID del administrador a retirar."""
        query = update.callback_query
        await query.edit_message_text(
            "👑 *Eliminar Administrador*\n\n"
            "Introduce el ID del administrador a eliminar:",
            parse_mode='Markdown'
        )
        application = context.application
        invoker_id = query.from_user.id

        if not hasattr(application, 'temp_handlers'):
            application.temp_handlers = {}

        async def user_id_input_handler(update_inner: Update, context_inner: ContextTypes.DEFAULT_TYPE):
            if update_inner.effective_user.id != invoker_id:
                return
            handler_tmp = application.temp_handlers.pop(invoker_id, None)
            if handler_tmp:
                application.remove_handler(handler_tmp)
            text = update_inner.message.text.strip()
            if text.isdigit():
                remove_id = int(text)
                if remove_id == self.super_admin_id:
                    await update_inner.message.reply_text("❌ No puedes eliminar al superadministrador.")
                    return
                if self.data_store.remove_admin(remove_id):
                    await update_inner.message.reply_text(f"✅ Usuario #{remove_id} dejó de ser administrador.")
                else:
                    await update_inner.message.reply_text("❌ Ese usuario no es administrador.")
            else:
                await update_inner.message.reply_text("❌ ID inválido. Operación cancelada.")

        handler = MessageHandler(filters.TEXT & ~filters.COMMAND, user_id_input_handler)
        application.temp_handlers[invoker_id] = handler
        application.add_handler(handler, group=0)

    async def handle_ban_by_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Solicita ID del usuario a banear."""
        query = update.callback_query
        await query.edit_message_text(
            "🚫 *Banear Usuario por ID*\n\n"
            "Introduce el ID del usuario que deseas banear:",
            parse_mode='Markdown'
        )
        application = context.application
        invoker_id = query.from_user.id

        if not hasattr(application, 'temp_handlers'):
            application.temp_handlers = {}

        async def user_id_input_handler(update_inner: Update, context_inner: ContextTypes.DEFAULT_TYPE):
            if update_inner.effective_user.id != invoker_id:
                return
            handler_tmp = application.temp_handlers.pop(invoker_id, None)
            if handler_tmp:
                application.remove_handler(handler_tmp)
            text = update_inner.message.text.strip()
            if text.isdigit():
                target_id = int(text)
                await self.process_ban(update_inner, context_inner, target_id)
            else:
                await update_inner.message.reply_text("❌ ID inválido. Operación cancelada.")

        handler = MessageHandler(filters.TEXT & ~filters.COMMAND, user_id_input_handler)
        application.temp_handlers[invoker_id] = handler
        application.add_handler(handler, group=0)

    async def handle_unban_by_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Solicita ID del usuario a desbanear."""
        query = update.callback_query
        await query.edit_message_text(
            "✅ *Desbanear Usuario por ID*\n\n"
            "Introduce el ID del usuario que deseas desbanear:",
            parse_mode='Markdown'
        )
        application = context.application
        invoker_id = query.from_user.id

        if not hasattr(application, 'temp_handlers'):
            application.temp_handlers = {}

        async def user_id_input_handler(update_inner: Update, context_inner: ContextTypes.DEFAULT_TYPE):
            if update_inner.effective_user.id != invoker_id:
                return
            handler_tmp = application.temp_handlers.pop(invoker_id, None)
            if handler_tmp:
                application.remove_handler(handler_tmp)
            text = update_inner.message.text.strip()
            if text.isdigit():
                target_id = int(text)
                await self.process_unban(update_inner, context_inner, target_id)
            else:
                await update_inner.message.reply_text("❌ ID inválido. Operación cancelada.")

        handler = MessageHandler(filters.TEXT & ~filters.COMMAND, user_id_input_handler)
        application.temp_handlers[invoker_id] = handler
        application.add_handler(handler, group=0)

    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja /add_admin <user_id>."""
        await try_delete_user_message(update)
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("Uso: /add_admin <ID>")
            return
        user_id = update.effective_user.id
        if not self.data_store.is_admin(user_id):
            await update.message.reply_text("No tienes permisos de administrador.")
            return
        target_id = int(context.args[0])
        if self.data_store.add_admin(target_id):
            await update.message.reply_text(f"✅ Usuario #{target_id} ahora es administrador.")
        else:
            await update.message.reply_text("❌ No se pudo añadir (tal vez ya es admin).")

    async def remove_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja /remove_admin <user_id>."""
        await try_delete_user_message(update)
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("Uso: /remove_admin <ID>")
            return
        user_id = update.effective_user.id
        if not self.data_store.is_admin(user_id):
            await update.message.reply_text("No tienes permisos de administrador.")
            return
        target_id = int(context.args[0])
        if self.data_store.remove_admin(target_id):
            await update.message.reply_text(f"✅ El usuario #{target_id} ya no es administrador.")
        else:
            await update.message.reply_text("❌ No se pudo eliminar (tal vez no era admin).")

# Comandos y funciones del bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el bot y muestra el mensaje de bienvenida."""
    await try_delete_user_message(update)
    user = update.effective_user
    user_id = user.id
    
    # Actualizar actividad del usuario
    db.update_user_activity(user_id)
    
    # Verificar si el usuario está baneado
    if user_id in db.users and db.users[user_id].get("banned", False):
        await delete_previous_and_send(context, user_id, "Lo sentimos, tu acceso a este bot ha sido restringido.")
        return ConversationHandler.END
    
    # Configurar menú de comandos
    await context.bot.set_my_commands([
        BotCommand("start", "Iniciar el bot"),
        BotCommand("find", "Buscar pareja para chatear"),
        BotCommand("end", "Finalizar chat actual"),
        BotCommand("stats", "Ver estadísticas"),
        BotCommand("gender", "Cambiar preferencia de género"),
        BotCommand("help", "Mostrar ayuda"),
        BotCommand("report", "Reportar usuario")
    ])
    
    # Configurar el botón de menú
    await context.bot.set_chat_menu_button(
        chat_id=user_id,
        menu_button=MenuButtonCommands()
    )
    
    welcome_message = (
        f"👋 ¡Hola {user.first_name}! Bienvenido/a a *Anonymous Chat Bot*.\n\n"
        "Este bot te permite chatear anónimamente con otras personas.\n\n"
        "*Instrucciones:*\n"
        "1️⃣ Primero debes seleccionar tu género\n"
        "2️⃣ Luego podrás buscar a alguien con quien chatear\n"
        "3️⃣ Una vez emparejado, podrás enviar mensajes, fotos, stickers y más\n"
        "4️⃣ Si deseas terminar la conversación, usa /end\n\n"
        "🔒 Tu identidad permanecerá anónima durante toda la conversación.\n"
        "💬 ¡Diviértete conociendo nuevas personas!"
    )
    
    # Verificar si el usuario ya ha seleccionado género
    if user_id in db.users and db.users[user_id].get("gender"):
        gender = db.users[user_id]["gender"]
        gender_name = get_gender_name(gender)
        gender_emoji = get_gender_emoji(gender)
        
        keyboard = [
            [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
            [InlineKeyboardButton("🔄 Cambiar Género", callback_data="change_gender")],
            [InlineKeyboardButton("📊 Estadísticas", callback_data="show_stats")]
        ]
        
        if db.is_admin(user_id):
            keyboard.append([InlineKeyboardButton("👑 Panel Admin", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await delete_previous_and_send(
            context, 
            user_id, 
            f"{welcome_message}\n\nTu género actual: {gender_emoji} {gender_name}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    else:
        # Si no tiene género seleccionado, mostrar opciones
        keyboard = [
            [InlineKeyboardButton("👨 Hombre", callback_data="gender_male")],
            [InlineKeyboardButton("👩 Mujer", callback_data="gender_female")],
            [InlineKeyboardButton("🧑 No Binario", callback_data="gender_non_binary")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await delete_previous_and_send(
            context,
            user_id,
            f"{welcome_message}\n\nPor favor, selecciona tu género:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return GENDER_SELECTION

async def gender_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Permite al usuario cambiar su género."""
    await try_delete_user_message(update)
    user_id = update.effective_user.id
    db.update_user_activity(user_id)
    
    # Verificar si el usuario está baneado
    if user_id in db.users and db.users[user_id].get("banned", False):
        await delete_previous_and_send(context, user_id, "Lo sentimos, tu acceso a este bot ha sido restringido.")
        return ConversationHandler.END

    # Preparar el mensaje y botones para selección de género
    keyboard = [
        [InlineKeyboardButton("👨 Hombre", callback_data="gender_male")],
        [InlineKeyboardButton("👩 Mujer", callback_data="gender_female")],
        [InlineKeyboardButton("🧑 No Binario", callback_data="gender_non_binary")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await delete_previous_and_send(
        context,
        user_id,
        "Por favor, selecciona tu género:",
        reply_markup=reply_markup
    )
    
    return GENDER_SELECTION

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    db.update_user_activity(user_id)
    
    if query.data == "gender_male":
        db.set_user_gender(user_id, "male")
        await query.edit_message_text("Has seleccionado: Hombre")
    elif query.data == "gender_female":
        db.set_user_gender(user_id, "female")
        await query.edit_message_text("Has seleccionado: Mujer")
    elif query.data == "gender_non_binary":
        db.set_user_gender(user_id, "non_binary")
        await query.edit_message_text("Has seleccionado: No Binario")
    
    # Guardar los datos actualizados
    db.save_data()
    
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra información de ayuda."""
    await try_delete_user_message(update)
    user_id = update.effective_user.id
    db.update_user_activity(user_id)
    
    # Verificar si el usuario está baneado
    if user_id in db.users and db.users[user_id].get("banned", False):
        await delete_previous_and_send(context, user_id, "Lo sentimos, tu acceso a este bot ha sido restringido.")
        return
    
    help_message = (
        "*Comandos disponibles:*\n"
        "/start - Iniciar el bot\n"
        "/find - Buscar una pareja para chatear\n"
        "/end - Finalizar la conversación actual\n"
        "/gender - Cambiar tu género\n"
        "/stats - Ver estadísticas del bot\n"
        "/report - Reportar a un usuario\n"
        "/help - Mostrar este mensaje de ayuda\n\n"
    )
    
    if db.is_admin(user_id):
        help_message += (
            "*Comandos de administrador:*\n"
            "/admin - Acceder al panel de administrador\n"
            "/ban <user_id> - Banear a un usuario\n"
            "/unban <user_id> - Desbanear a un usuario\n"
            "/add_admin <user_id> - Añadir administrador\n"
            "/remove_admin <user_id> - Eliminar administrador\n"
        )
        
        if db.is_super_admin(user_id):
            help_message += (
                "*Comandos de superadministrador:*\n"
                "/add_admin <user_id> - Añadir administrador\n"
                "/remove_admin <user_id> - Eliminar administrador\n"
            )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await delete_previous_and_send(
        context, 
        user_id, 
        help_message, 
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def find_partner_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Comando para buscar pareja."""
    await try_delete_user_message(update)
    # Comprobar explícitamente que tenemos un mensaje
    if not update.message:
        logger.warning("find_partner_command llamado sin un mensaje válido")
        return ConversationHandler.END
        
    # Asegúrate de tener el contexto correcto antes de pasar a find_partner
    user_id = update.effective_user.id
    db.update_user_activity(user_id)
    
    # Verificar si el usuario está baneado
    if user_id in db.users and db.users[user_id].get("banned", False):
        await delete_previous_and_send(context, user_id, "Lo sentimos, tu acceso a este bot ha sido restringido.")
        return ConversationHandler.END
    
    return await find_partner(update, context)

async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Función para buscar y emparejar usuarios."""
    try:
        if isinstance(update, Update) and update.callback_query:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            message = query.message
        else:
            if not update.message:
                logger.error("find_partner llamado con update sin message ni callback_query")
                return ConversationHandler.END
                
            user_id = update.effective_user.id
            message = update.message
        
        db.update_user_activity(user_id)
        
        # Verificar si el usuario está baneado
        if user_id in db.users and db.users[user_id].get("banned", False):
            if isinstance(update, Update) and update.callback_query:
                await query.edit_message_text("Lo sentimos, tu acceso a este bot ha sido restringido.")
            else:
                await delete_previous_and_send(context, user_id, "Lo sentimos, tu acceso a este bot ha sido restringido.")
            return ConversationHandler.END
    
        # Obtener el género del usuario
        _user_gender = db.users[user_id]["gender"]

        # Mostrar estadísticas por género antes de emparejar
        waiting_counts = db.get_waiting_counts()

        gender_stats_msg = (
            "📊 *Usuarios esperando por género:*\n"
            f"👨 Hombres: {waiting_counts['male']}\n"
            f"👩 Mujeres: {waiting_counts['female']}\n"
            f"🧑 No Binarios: {waiting_counts['non_binary']}\n\n"
            "¿Con qué género te gustaría chatear?"
        )

        keyboard = [
            [InlineKeyboardButton("👨 Hombre", callback_data="match_male")],
            [InlineKeyboardButton("👩 Mujer", callback_data="match_female")],
            [InlineKeyboardButton("🧑 No Binario", callback_data="match_non_binary")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if isinstance(update, Update) and update.callback_query:
            await query.edit_message_text(gender_stats_msg, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await delete_previous_and_send(
                context,
                user_id,
                gender_stats_msg,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        return WAITING_MATCH

    except Exception as e:
        logger.exception(f"Error en find_partner: {e}")
        if isinstance(update, Update) and hasattr(update, "message") and update.message:
            await delete_previous_and_send(context, user_id, "Ha ocurrido un error. Por favor, inténtalo nuevamente.")
        return ConversationHandler.END

async def match_by_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Empareja usuarios según preferencia de género."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    preferred_gender = query.data.split("_")[1]  # match_male -> male
    
    # Corregir la abreviatura 'non' a 'non_binary' si es necesario
    if preferred_gender == 'non':
        preferred_gender = 'non_binary'
    
    # Obtener el género del usuario
    user_gender = db.users[user_id]["gender"]
    
    # Crear la clave combinada para el emparejamiento específico
    # Format: "seeking_gender" 
    # Ejemplo: "seeking_male", "seeking_female" - indica a quién está buscando
    waiting_key = f"seeking_{preferred_gender}"
    
    # Inicializar los diccionarios si no existen
    if not hasattr(db, 'gender_waiting_users'):
        db.gender_waiting_users = {}
    
    # Asegurarse de que todas las claves de espera existan
    for gender in ["seeking_male", "seeking_female", "seeking_non_binary"]:
        if gender not in db.gender_waiting_users:
            db.gender_waiting_users[gender] = []
    
    # Primero, buscar si hay alguien buscando mi género
    seeking_my_gender = f"seeking_{user_gender}"
    matched_partner = None
    
    if seeking_my_gender in db.gender_waiting_users and db.gender_waiting_users[seeking_my_gender]:
        # Buscar entre quienes esperan mi género
        for idx, waiting_user_id in enumerate(db.gender_waiting_users[seeking_my_gender]):
            waiting_user_gender = db.users[waiting_user_id]["gender"]
            # Si su género coincide con el que yo busco, emparejarnos
            if waiting_user_gender == preferred_gender:
                matched_partner = waiting_user_id
                # Remover de la lista de espera
                db.gender_waiting_users[seeking_my_gender].pop(idx)
                break
    
    # Si encontramos pareja
    if matched_partner:
        db.create_chat(user_id, matched_partner)
        
        # Limpiar este usuario de todas las listas de espera
        for key in db.gender_waiting_users:
            if user_id in db.gender_waiting_users[key]:
                db.gender_waiting_users[key].remove(user_id)
        
        # Enviar mensaje a ambos usuarios usando delete_previous_and_send para limpiar la conversación
        keyboard = [[InlineKeyboardButton("❌ Finalizar Chat", callback_data="end_chat")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        partner_gender = db.users[matched_partner]["gender"]
        
        # Limpiar el chat para el usuario actual
        await delete_previous_and_send(
            context,
            user_id,
            f"🎉 *¡Nueva conversación iniciada!*\n\n"
            f"Has sido emparejado con un {get_gender_emoji(partner_gender)} {get_gender_name(partner_gender)}.\n\n"
            f"Tu identidad es anónima. Puedes comenzar a chatear ahora.",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            clear_all=True  # Esto borrará todos los mensajes anteriores
        )
        
        # Limpiar el chat para la pareja
        await delete_previous_and_send(
            context,
            matched_partner,
            f"🎉 *¡Nueva conversación iniciada!*\n\n"
            f"Has sido emparejado con un {get_gender_emoji(user_gender)} {get_gender_name(user_gender)}.\n\n"
            f"Tu identidad es anónima. Puedes comenzar a chatear ahora.",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            clear_all=True  # Esto borrará todos los mensajes anteriores
        )
        
        return IN_CHAT
    
    # Si no hay pareja, ponernos en lista de espera
    # Limpiar este usuario de todas las listas de espera primero
    for key in db.gender_waiting_users:
        if user_id in db.gender_waiting_users[key]:
            db.gender_waiting_users[key].remove(user_id)
    
    # Añadir al usuario a la lista de quienes buscan este género
    db.gender_waiting_users[waiting_key].append(user_id)
    
    # Mostrar mensaje de espera
    keyboard = [[InlineKeyboardButton("❌ Cancelar Búsqueda", callback_data="cancel_search")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    gender_name = get_gender_name(preferred_gender)
    await query.edit_message_text(
        f"⏳ Esperando a que se conecte un {get_gender_emoji(preferred_gender)} {gender_name}...\n\nPuedes cancelar la búsqueda en cualquier momento.",
        reply_markup=reply_markup
    )
    
    # Marcar en la BD que el usuario está esperando
    if user_id in db.users:
        db.users[user_id]["waiting_for_match"] = True
    
    db.save_data()
    return WAITING_MATCH

async def end_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finaliza el chat actual."""
    await try_delete_user_message(update)
    user_id = update.effective_user.id
    return await end_chat(update, context, user_id)

async def end_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None) -> int:
    """Finaliza un chat activo."""
    if user_id is None:
        if isinstance(update, Update) and update.callback_query:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
        else:
            user_id = update.effective_user.id
    
    db.update_user_activity(user_id)
    
    partner_id = db.end_chat(user_id)
    
    if partner_id:
        # Informar a ambos usuarios
        keyboard = [
            [InlineKeyboardButton("🔍 Buscar Otra Pareja", callback_data="find_partner")],
            [InlineKeyboardButton("📊 Estadísticas", callback_data="show_stats")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Usar delete_previous_and_send con clear_all=True para limpiar todos los mensajes
        await delete_previous_and_send(
            context,
            user_id,
            "❌ Chat finalizado. La otra persona ha sido notificada.",
            reply_markup=reply_markup,
            clear_all=True  # Limpiar todo al finalizar chat
        )
        
        await delete_previous_and_send(
            context,
            partner_id,
            "❌ Tu pareja ha finalizado el chat.",
            reply_markup=reply_markup,
            clear_all=True  # Limpiar todo al finalizar chat
        )
        
        return ConversationHandler.END
    else:
        keyboard = [
            [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
            [InlineKeyboardButton("📊 Estadísticas", callback_data="show_stats")],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.edit_message_text(
                "No estás en ninguna conversación actualmente.",
                reply_markup=reply_markup
            )
        else:
            await delete_previous_and_send(
                context,
                user_id,
                "No estás en ninguna conversación actualmente.",
                reply_markup=reply_markup
            )
        
        return ConversationHandler.END

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la búsqueda de pareja."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    db.update_user_activity(user_id)
    
    # Remover de las listas de espera antiguas
    db.remove_from_waiting(user_id)
    
    # Remover de las nuevas listas de espera
    if hasattr(db, 'gender_waiting_users'):
        for key in db.gender_waiting_users:
            if user_id in db.gender_waiting_users[key]:
                db.gender_waiting_users[key].remove(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="show_stats")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "❌ Búsqueda cancelada. ¿Qué deseas hacer ahora?",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el menú principal."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    db.update_user_activity(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🔍 Buscar Pareja", callback_data="find_partner")],
        [InlineKeyboardButton("🔄 Cambiar Género", callback_data="change_gender")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="show_stats")]
    ]
    
    if db.is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Panel Admin", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🏠 *Menú Principal*\n\nSelecciona una opción:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para mostrar estadísticas."""
    await try_delete_user_message(update)
    return await show_stats(update, context)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra las estadísticas del bot."""
    if isinstance(update, Update) and update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
    
    db.update_user_activity(user_id)
    
    # Calcular estadísticas
    uptime = format_time_difference(time.time() - db.stats["start_time"])
    waiting_counts = db.get_waiting_counts()
    active_counts = db.get_active_counts()
    gender_stats = db.stats["gender_stats"]
    
    # Preparar mensaje de estadísticas
    stats_message = (
        "📊 *Estadísticas del Bot*\n\n"
        f"👥 *Usuarios activos ahora:* {len(db.active_chats) // 2 + sum(len(users) for users in db.waiting_users.values())}\n"
        f"💬 *Conversaciones activas:* {len(db.active_chats) // 2}\n\n"
        f"*Usuarios en espera:*\n"
        f"👨 Hombres: {waiting_counts['male']}\n"
        f"👩 Mujeres: {waiting_counts['female']}\n"
        f"🧑 No Binarios: {waiting_counts['non_binary']}\n\n"
        f"*Conversaciones por género:*\n"
        f"👨 Hombres: {active_counts['male']}\n"
        f"👩 Mujeres: {active_counts['female']}\n"
        f"🧑 No Binarios: {active_counts['non_binary']}\n\n"
        f"*Usuarios totales por género:*\n"
        f"👨 Hombres: {gender_stats['male']}\n"
        f"👩 Mujeres: {gender_stats['female']}\n"
        f"🧑 No Binarios: {gender_stats['non_binary']}\n\n"
        f"📝 *Total de mensajes:* {db.stats['messages_sent']}\n"
        f"🔄 *Total de chats iniciados:* {db.stats['total_chats']}\n"
        f"👥 *Usuarios únicos totales:* {db.stats['total_users']}\n"
        f"👤 *Usuarios activos (24h):* {db.stats['daily_active_users']}\n\n"
        f"⏱️ *Tiempo en línea:* {uptime}\n"
        f"🔝 *Pico de usuarios:* {db.stats['peak_concurrent_users']} "
        f"({db.stats['peak_time'] if db.stats['peak_time'] else 'No registrado'})"
    )
    
    keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if isinstance(update, Update) and update.callback_query:
        await query.edit_message_text(
            stats_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            stats_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Comando para reportar a un usuario."""
    await try_delete_user_message(update)
    user_id = update.effective_user.id
    db.update_user_activity(user_id)
    
    # Verificar si el usuario está en un chat activo
    if user_id not in db.active_chats:
        await update.message.reply_text(
            "Solo puedes reportar a un usuario mientras estás en una conversación con él."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🚨 *Reporte de Usuario*\n\n"
        "Por favor, describe el motivo del reporte. Sé específico sobre el comportamiento inapropiado:",
        parse_mode='Markdown'
    )
    
    return REPORT_REASON

async def report_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el motivo del reporte."""
    user_id = update.effective_user.id
    reason = update.message.text
    
    # Guardar el motivo en el contexto
    context.user_data['report_reason'] = reason
    
    await update.message.reply_text(
        "Por favor, envía una captura de pantalla como evidencia del comportamiento reportado.\n"
        "Si no tienes una captura, simplemente escribe 'no tengo evidencia'."
    )
    
    return REPORT_EVIDENCE

async def report_evidence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la evidencia del reporte."""
    user_id = update.effective_user.id
    reason = context.user_data.get('report_reason', "No especificado")
    
    # Verificar si el usuario está en un chat
    if user_id not in db.active_chats:
        await update.message.reply_text("El chat ha finalizado. No se puede completar el reporte.")
        return ConversationHandler.END
    
    reported_id = db.active_chats[user_id]
    evidence_file_id = None
    
    if update.message.photo:
        evidence_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        evidence_file_id = update.message.document.file_id
    
    # Crear el reporte
    report_id = db.add_report(user_id, reported_id, reason, evidence_file_id)
    
    # Notificar a los administradores
    for admin_id in db.admins:
        try:
            if evidence_file_id:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=evidence_file_id,
                    caption=f"🚨 *Nuevo Reporte #{report_id}*\n\n"
                            f"*De:* Usuario #{user_id}\n"
                            f"*Contra:* Usuario #{reported_id}\n"
                            f"*Motivo:* {reason}",
                    parse_mode='Markdown'
                )
            else:
                                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🚨 *Nuevo Reporte #{report_id}*\n\n"
                         f"*De:* Usuario #{user_id}\n"
                         f"*Contra:* Usuario #{reported_id}\n"
                         f"*Motivo:* {reason}\n"
                         f"*Evidencia:* No proporcionada",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error al enviar reporte a admin {admin_id}: {e}")
    
    # Confirmar al usuario
    await update.message.reply_text(
        "✅ Tu reporte ha sido enviado a los administradores. Gracias por ayudar a mantener la comunidad segura."
    )
    
    return ConversationHandler.END

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para acceder al panel de administrador."""
    await try_delete_user_message(update)
    # Simplemente llamar al método de AdminCommands
    await admin_cmds.admin_panel(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el panel de administrador."""
    await try_delete_user_message(update)
    if isinstance(update, Update) and update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        if isinstance(update, Update) and update.callback_query:
            await query.edit_message_text("No tienes permisos para acceder a esta función.")
        else:
            await update.message.reply_text("No tienes permisos para acceder a esta función.")
        return
    
    # Obtener estadísticas para el panel admin
    total_users = db.stats["total_users"]
    active_chats = len(db.active_chats) // 2
    pending_reports = sum(1 for r in db.reports if r.get("status") == "pending")
    
    admin_message = (
        "👑 *Panel de Administrador*\n\n"
        f"👤 Total de usuarios: {total_users}\n"
        f"💬 Conversaciones activas: {active_chats}\n"
        f"🚨 Reportes pendientes: {pending_reports}\n\n"
        "Selecciona una opción:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Ver Estadísticas Detalladas", callback_data="admin_stats")],
        [InlineKeyboardButton("📋 Ver Reportes", callback_data="view_reports")]
    ]
    
    if db.is_super_admin(user_id):
        keyboard.append([InlineKeyboardButton("👥 Gestionar Administradores", callback_data="manage_admins")])
    
    keyboard.append([InlineKeyboardButton("🏠 Volver al Menú", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if isinstance(update, Update) and update.callback_query:
        await query.edit_message_text(admin_message, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(admin_message, parse_mode='Markdown', reply_markup=reply_markup)

async def view_reports(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los reportes recibidos."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_admin(user_id):
        await query.edit_message_text("No tienes permisos para acceder a esta función.")
        return
    
    # Obtener los reportes pendientes
    pending_reports = [r for r in db.reports if r.get("status") == "pending"]
    
    if not pending_reports:
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "No hay reportes pendientes de revisión.",
            reply_markup=reply_markup
        )
        return
    
    # Mostrar el primer reporte pendiente
    report = pending_reports[0]
    report_id = db.reports.index(report)
    
    reporter_id = report["reporter_id"]
    reported_id = report["reported_id"]
    reason = report["reason"]
    timestamp = report["timestamp"]
    evidence_file_id = report.get("evidence_file_id")
    
    report_text = (
        f"🚨 *Reporte #{report_id}*\n\n"
        f"*De:* Usuario #{reporter_id}\n"
        f"*Contra:* Usuario #{reported_id}\n"
        f"*Fecha:* {timestamp}\n"
        f"*Motivo:* {reason}\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Resolver", callback_data=f"resolve_report_{report_id}"),
            InlineKeyboardButton("❌ Descartar", callback_data=f"dismiss_report_{report_id}")
        ],
        [
            InlineKeyboardButton("🚫 Banear Usuario", callback_data=f"ban_user_{reported_id}")
        ],
        [InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if evidence_file_id:
        try:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=user_id,
                photo=evidence_file_id,
                caption=report_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error al enviar foto de reporte: {e}")
            await query.edit_message_text(
                report_text + "\n\n*Evidencia:* Disponible pero no se pudo cargar",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    else:
        await query.edit_message_text(
            report_text + "\n\n*Evidencia:* No proporcionada",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def handle_report_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las acciones sobre reportes (resolver, descartar)."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_admin(user_id):
        await query.edit_message_text("No tienes permisos para acceder a esta función.")
        return
    
    action, report_id = query.data.split("_")[0], int(query.data.split("_")[2])
    
    if report_id >= len(db.reports):
        await query.edit_message_text("Este reporte ya no existe.")
        return
    
    report = db.reports[report_id]
    
    if action == "resolve":
        report["status"] = "resolved"
        report["resolved_by"] = user_id
        report["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_msg = "resuelto"
    else:  # dismiss
        report["status"] = "dismissed"
        report["dismissed_by"] = user_id
        report["dismissed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_msg = "descartado"
    
    db.save_data()
    
    keyboard = [[InlineKeyboardButton("🔙 Volver a Reportes", callback_data="view_reports")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"El reporte #{report_id} ha sido marcado como {status_msg}.",
        reply_markup=reply_markup
    )

async def ban_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Banea a un usuario desde el panel de reportes."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_admin(user_id):
        await query.edit_message_text("No tienes permisos para acceder a esta función.")
        return
    
    target_id = int(query.data.split("_")[2])
    
    if db.ban_user(target_id):
        # Si el usuario estaba en un chat, notificar a su pareja
        if target_id in db.active_chats:
            partner_id = db.active_chats[target_id]
            db.end_chat(target_id)
            
            keyboard = [
                [InlineKeyboardButton("🔍 Buscar Otra Pareja", callback_data="find_partner")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=partner_id,
                text="❗ Tu pareja ha sido desconectada por un administrador.",
                reply_markup=reply_markup
            )
        
        keyboard = [[InlineKeyboardButton("🔙 Volver a Reportes", callback_data="view_reports")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ Usuario #{target_id} ha sido baneado correctamente.",
            reply_markup=reply_markup
        )
    else:
        keyboard = [[InlineKeyboardButton("🔙 Volver a Reportes", callback_data="view_reports")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ No se pudo banear al usuario #{target_id}. Puede ser un administrador o ya está baneado.",
            reply_markup=reply_markup
        )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra estadísticas detalladas para administradores."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_admin(user_id):
        await query.edit_message_text("No tienes permisos para acceder a esta función.")
        return
    
    # Estadísticas detalladas
    content_types = db.stats["content_types"]
    gender_stats = db.stats["gender_stats"]
    
    stats_message = (
        "📊 *Estadísticas Detalladas*\n\n"
        f"👥 *Usuarios registrados:* {db.stats['total_users']}\n"
        f"👤 *Usuarios activos (24h):* {db.stats['daily_active_users']}\n"
        f"💬 *Chats totales:* {db.stats['total_chats']}\n"
        f"📝 *Mensajes enviados:* {db.stats['messages_sent']}\n\n"
        f"*Distribución por género:*\n"
        f"👨 Hombres: {gender_stats['male']} ({int(gender_stats['male']/max(1, db.stats['total_users'])*100)}%)\n"
        f"👩 Mujeres: {gender_stats['female']} ({int(gender_stats['female']/max(1, db.stats['total_users'])*100)}%)\n"
        f"🧑 No Binarios: {gender_stats['non_binary']} ({int(gender_stats['non_binary']/max(1, db.stats['total_users'])*100)}%)\n\n"
        f"*Tipos de contenido:*\n"
        f"💬 Texto: {content_types['text']}\n"
        f"🖼️ Fotos: {content_types['photo']}\n"
        f"😎 Stickers: {content_types['sticker']}\n"
        f"🎤 Audio/Voz: {content_types['voice'] + content_types['audio']}\n"
        f"📹 Videos/GIFs: {content_types['video'] + content_types['animation']}\n"
        f"📄 Documentos: {content_types['document']}\n\n"
        f"🚨 *Reportes:*\n"
        f"- Pendientes: {sum(1 for r in db.reports if r.get('status') == 'pending')}\n"
        f"- Resueltos: {sum(1 for r in db.reports if r.get('status') == 'resolved')}\n"
        f"- Descartados: {sum(1 for r in db.reports if r.get('status') == 'dismissed')}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(stats_message, parse_mode='Markdown', reply_markup=reply_markup)

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra panel para gestionar administradores."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_super_admin(user_id):
        await query.edit_message_text("Solo el superadministrador puede acceder a esta función.")
        return
    
    admin_list = "\n".join([f"• Admin #{admin_id}" for admin_id in db.admins if admin_id != SUPER_ADMIN_ID])
    if not admin_list:
        admin_list = "No hay administradores adicionales."
    
    admin_message = (
        "👑 *Gestión de Administradores*\n\n"
        f"*Administradores actuales:*\n{admin_list}\n\n"
        "¿Qué acción deseas realizar?"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Añadir Admin", callback_data="add_admin")],
        [InlineKeyboardButton("➖ Eliminar Admin", callback_data="remove_admin")],
        [InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(admin_message, parse_mode='Markdown', reply_markup=reply_markup)

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de añadir administrador."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_super_admin(user_id):
        await query.edit_message_text("Solo el superadministrador puede acceder a esta función.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "Por favor, escribe el ID del usuario que quieres añadir como administrador:"
    )
    
    return ADMIN_ADD

async def add_admin_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finaliza el proceso de añadir administrador."""
    user_id = update.effective_user.id
    
    if not db.is_super_admin(user_id):
        await update.message.reply_text("Solo el superadministrador puede acceder a esta función.")
        return ConversationHandler.END
    
    try:
        new_admin_id = int(update.message.text.strip())
        
        if db.add_admin(new_admin_id):
            await update.message.reply_text(f"✅ Usuario #{new_admin_id} añadido como administrador.")
        else:
            await update.message.reply_text(f"❌ El usuario #{new_admin_id} ya es administrador.")
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, introduce un ID de usuario válido (número).")
    
    # Volver al panel de administradores
    keyboard = [[InlineKeyboardButton("🔙 Volver a Gestión de Admins", callback_data="manage_admins")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("¿Qué deseas hacer ahora?", reply_markup=reply_markup)
    
    return ConversationHandler.END

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de eliminar administrador."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_super_admin(user_id):
        await query.edit_message_text("Solo el superadministrador puede acceder a esta función.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "Por favor, escribe el ID del administrador que quieres eliminar:"
    )
    
    return ADMIN_REMOVE

async def remove_admin_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finaliza el proceso de eliminar administrador."""
    user_id = update.effective_user.id
    
    if not db.is_super_admin(user_id):
        await update.message.reply_text("Solo el superadministrador puede acceder a esta función.")
        return ConversationHandler.END
    
    try:
        admin_id = int(update.message.text.strip())
        
        if admin_id == SUPER_ADMIN_ID:
            await update.message.reply_text("❌ No puedes eliminar al superadministrador.")
        elif db.remove_admin(admin_id):
            await update.message.reply_text(f"✅ Usuario #{admin_id} eliminado de administradores.")
        else:
            await update.message.reply_text(f"❌ El usuario #{admin_id} no es administrador.")
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, introduce un ID de usuario válido (número).")
    
    # Volver al panel de administradores
    keyboard = [[InlineKeyboardButton("🔙 Volver a Gestión de Admins", callback_data="manage_admins")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("¿Qué deseas hacer ahora?", reply_markup=reply_markup)
    
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los mensajes enviados por los usuarios."""
    user_id = update.effective_user.id
    db.update_user_activity(user_id)
    
    # Verificar si el usuario está baneado
    if user_id in db.users and db.users[user_id].get("banned", False):
        await delete_previous_and_send(context, user_id, "Lo sentimos, tu acceso a este bot ha sido restringido.")
        return
    
    # Verificar si el usuario está en un chat activo
    if user_id in db.active_chats:
        partner_id = db.active_chats[user_id]
        
        # Actualizar estadísticas de mensajes
        message_type = "text"
        if update.message.text:
            message_type = "text"
        elif update.message.sticker:
            message_type = "sticker"
        elif update.message.photo:
            message_type = "photo"
        elif update.message.voice:
            message_type = "voice"
        elif update.message.video:
            message_type = "video"
        elif update.message.animation:
            message_type = "animation"
        elif update.message.document:
            message_type = "document"
        elif update.message.audio:
            message_type = "audio"
        
        db.update_message_stats(message_type)
        
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
            [InlineKeyboardButton("📊 Estadísticas", callback_data="show_stats")],
            [InlineKeyboardButton("ℹ️ Ayuda", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await delete_previous_and_send(
            context,
            user_id,
            "No estás en una conversación actualmente. ¿Deseas buscar una pareja para chatear?",
            reply_markup=reply_markup
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja las pulsaciones de botones."""
    query = update.callback_query
    
    # Callbacks específicos que ya tienen sus propias funciones
    if query.data == "find_partner":
        return await find_partner(update, context)
    elif query.data.startswith("gender_"):
        return await set_gender(update, context)
    elif query.data.startswith("match_"):
        return await match_by_gender(update, context)
    elif query.data == "end_chat":
        return await end_chat(update, context, None)
    elif query.data == "cancel_search":
        return await cancel_search(update, context)
    elif query.data == "main_menu":
        await main_menu(update, context)
        return ConversationHandler.END
    elif query.data == "show_stats":
        await show_stats(update, context)
        return ConversationHandler.END
    elif query.data == "change_gender":
        await gender_command(update, context)
        return GENDER_SELECTION
    # Admin panel callbacks - Usar la instancia de AdminCommands
    elif query.data == "admin_panel" or query.data.startswith("admin_"):
        # Redirigir todos los callbacks admin al handler especializado
        await admin_cmds.admin_callback(update, context)
        return ConversationHandler.END
    elif query.data == "help":
        await query.answer()
        help_message = (
            "*Comandos disponibles:*\n"
            "/start - Iniciar el bot\n"
            "/find - Buscar una pareja para chatear\n"
            "/end - Finalizar la conversación actual\n"
            "/gender - Cambiar tu género\n"
            "/stats - Ver estadísticas del bot\n"
            "/report - Reportar a un usuario\n"
            "/help - Mostrar este mensaje de ayuda\n\n"
        )
        
        if db.is_admin(query.from_user.id):
            help_message += (
                "*Comandos de administrador:*\n"
                "/admin - Acceder al panel de administrador\n"
                "/ban <user_id> - Banear a un usuario\n"
                "/unban <user_id> - Desbanear a un usuario\n"
            )
        
        keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_message, parse_mode='Markdown', reply_markup=reply_markup)
        return ConversationHandler.END
    
    # Si llegamos aquí, es un callback no manejado
    await query.answer(f"Acción no reconocida: {query.data}")
    logger.warning(f"Callback no manejado: {query.data} de usuario {query.from_user.id}")
    return ConversationHandler.END

def main() -> None:
    """Función principal para iniciar el bot."""
    # Crear la aplicación
    application = Application.builder().token(TOKEN).build()

    # Inicializar y registrar los comandos de administrador
    global admin_cmds  # Hacemos la variable global para accederla desde otras funciones
    admin_cmds = AdminCommands(db)
    admin_cmds.register_handlers(application)

    # Manejadores de conversación
    # ...existing code...
    
    # Comandos básicos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("end", end_chat_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # Añadir manejadores de conversación
    # Manejador de conversación para selección de género
    gender_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("gender", gender_command),
            CallbackQueryHandler(set_gender, pattern="^gender_")
        ],
        states={
            GENDER_SELECTION: [CallbackQueryHandler(set_gender, pattern="^gender_")]
        },
        fallbacks=[CommandHandler("cancel", lambda _u, _c: ConversationHandler.END)]
    )
    
    # Manejador de conversación para búsqueda de pareja
    find_partner_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("find", find_partner_command),
            CallbackQueryHandler(find_partner, pattern="^find_partner$")
        ],
        states={
            GENDER_SELECTION: [CallbackQueryHandler(set_gender, pattern="^gender_")],
            WAITING_MATCH: [
                CallbackQueryHandler(match_by_gender, pattern="^match_"),
                CallbackQueryHandler(cancel_search, pattern="^cancel_search$")
            ],
            IN_CHAT: [CallbackQueryHandler(end_chat_command, pattern="^end_chat$")]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    
    # Manejador de conversación para reportes
    report_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("report", report_command)],
        states={
            REPORT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_reason)],
            REPORT_EVIDENCE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL | filters.TEXT & ~filters.COMMAND, report_evidence)
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    
    # Manejador de conversación para añadir/eliminar admins
    admin_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_admin_start, pattern="^add_admin$"),
            CallbackQueryHandler(remove_admin_start, pattern="^remove_admin$")
        ],
        states={
            ADMIN_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_finish)],
            ADMIN_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_finish)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=True
    )

    application.add_handler(gender_conv_handler)
    application.add_handler(find_partner_conv_handler)
    application.add_handler(report_conv_handler)
    application.add_handler(admin_conv_handler)
    
    # Callback general para botones - Asegúrate de que este sea el último handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Manejo de mensajes
    class ShouldHandleMessageFilter(filters.MessageFilter):
        def filter(self, message):
            user_id = message.from_user.id
            # No procesar si el usuario está en un proceso de entrada de ID admin
            return not (hasattr(application, 'temp_handlers') and user_id in application.temp_handlers)

    should_handle_filter = ShouldHandleMessageFilter()
    
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND & should_handle_filter,
            handle_message
        )
    )

    # Iniciar el bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# Añadir esto antes de la función main()

# Rastreo de mensajes
last_bot_messages = {}  # {user_id: [{"chat_id": chat_id, "message_id": message_id}, ...]}
MAX_TRACKED_MESSAGES = 10  # Número máximo de mensajes a rastrear por usuario

async def delete_previous_and_send(context, user_id, text, reply_markup=None, parse_mode=None, clear_all=False):
    """Elimina mensajes anteriores y envía uno nuevo.
    
    Si clear_all=True, intenta eliminar todos los mensajes rastreados.
    """
    if user_id in last_bot_messages:
        # Determinar cuántos mensajes borrar
        msgs_to_delete = last_bot_messages[user_id]
        
        if not clear_all:
            # Si no es clear_all, solo borrar el último
            msgs_to_delete = msgs_to_delete[-1:]
        
        # Borrar mensajes
        for msg_info in msgs_to_delete:
            try:
                chat_id = msg_info["chat_id"]
                message_id = msg_info["message_id"]
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.debug(f"No se pudo eliminar mensaje para {user_id}: {e}")
        
        # Limpiar la lista si borramos todos
        if clear_all:
            last_bot_messages[user_id] = []
    
    # Enviar nuevo mensaje
    message = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    
    # Registrar el nuevo mensaje
    if user_id not in last_bot_messages:
        last_bot_messages[user_id] = []
    
    last_bot_messages[user_id].append({
        "chat_id": message.chat_id,
        "message_id": message.message_id
    })
    
    # Mantener el registro dentro de un tamaño razonable
    if len(last_bot_messages[user_id]) > MAX_TRACKED_MESSAGES:
        last_bot_messages[user_id] = last_bot_messages[user_id][-MAX_TRACKED_MESSAGES:]
    
    return message


async def try_delete_user_message(update: Update):
    """Intenta eliminar el mensaje del usuario."""
    try:
        if hasattr(update, 'message') and update.message:
            await update.message.delete()
    except Exception as e:
        logger.debug(f"No se pudo eliminar el mensaje del usuario: {e}")

# Rastreo de mensajes
last_bot_messages = {}  # {user_id: [{"chat_id": chat_id, "message_id": message_id}, ...]}

if __name__ == "__main__":
    main()
