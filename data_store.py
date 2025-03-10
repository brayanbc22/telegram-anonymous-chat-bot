#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import time
import logging
from datetime import datetime

# Configuración de logging
logger = logging.getLogger(__name__)

# Rutas de archivos para persistencia
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")

class DataStore:
    def __init__(self, super_admin_id):
        """Inicializa el almacén de datos."""
        self.super_admin_id = super_admin_id
        self.users = {}  # {user_id: {"gender": "male", "role": "user", "paired_with": None}}
        self.waiting_users = {"male": [], "female": [], "non_binary": []}
        self.active_chats = {}  # {user_id: partner_id}
        self.gender_waiting_users = {}
        self.admins = set([super_admin_id])  # Conjunto de IDs de administradores
        self.reports = []  # Lista de reportes
        self.spam_control = {}  # {user_id: {"message_count": 0, "first_message_time": timestamp, "cooldown_until": timestamp}}
        self.stats = {
            "total_users": 0,
            "total_chats": 0,
            "active_sessions": 0,
            "messages_sent": 0,
            "start_time": time.time(),
            "daily_active_users": 0,
            "user_last_active": {},
            "peak_concurrent_users": 0,
            "peak_time": None,
            "content_types": {
                "text": 0, "sticker": 0, "photo": 0, "voice": 0,
                "video": 0, "animation": 0, "document": 0, "audio": 0
            },
            "gender_stats": {"male": 0, "female": 0, "non_binary": 0}
        }
        self.super_admin_id = super_admin_id
        self.load_data()

        # Reiniciar tiempo de inicio para reflejar el arranque actual del bot
        self.stats["start_time"] = time.time()

    def load_data(self):
        """Carga datos desde archivos JSON si existen."""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if os.path.isfile(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                self.users = json.load(f)
        if os.path.isfile(STATS_FILE):
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                self.stats = json.load(f)
        if os.path.isfile(REPORTS_FILE):
            with open(REPORTS_FILE, "r", encoding="utf-8") as f:
                self.reports = json.load(f)
        
        # Verificar que self.users es un diccionario
        if not isinstance(self.users, dict):
            logger.warning("users.json no tiene formato de diccionario. Reiniciando a vacío.")
            self.users = {}
        
        # Cargar admins desde self.users
        for uid, data in self.users.items():
            if isinstance(data, dict) and data.get("role") == "admin":
                self.admins.add(int(uid))
        
        logger.info(f"Datos cargados: {len(self.users)} usuarios, {len(self.admins)} administradores, {len(self.active_chats)/2} chats activos")

    def add_to_waiting_target(self, user_id, target_gender):
        """Añade un usuario a la lista de espera del género objetivo."""
        # Asegurarnos que el usuario no está en ninguna lista de espera
        self.remove_from_waiting(user_id)
        
        # Añadir al usuario a la lista del género que está buscando
        if target_gender not in self.waiting_users:
            self.waiting_users[target_gender] = []
        
        self.waiting_users[target_gender].append(user_id)

    def save_data(self):
        """Guarda datos a archivos JSON."""
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.users, f, ensure_ascii=False, indent=2)
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.reports, f, ensure_ascii=False, indent=2)

    def update_daily_active_users(self):
        """Actualiza el contador de usuarios activos diarios."""
        current_time = time.time()
        one_day_ago = current_time - 86400  # 24 horas en segundos
        
        # Contar usuarios activos en las últimas 24 horas
        active_users = 0
        for user_id, last_active in self.stats["user_last_active"].items():
            if last_active > one_day_ago:
                active_users += 1
        
        self.stats["daily_active_users"] = active_users

    def update_user_activity(self, user_id):
        """Actualiza la actividad del usuario y las estadísticas."""
        current_time = time.time()
        
        # Registrar al usuario si es nuevo
        if user_id not in self.users:
            self.users[user_id] = {
                "role": "user",
                "gender": None,
                "joined_date": current_time,
                "waiting_for_match": False,
                "paired_with": None,
                "first_seen": current_time,
                "last_active": current_time
            }
            self.stats["total_users"] += 1
        else:
            self.users[user_id]["last_active"] = current_time
        
        # Actualizar última actividad
        self.stats["user_last_active"][str(user_id)] = current_time
        
        # Actualizar usuarios activos diarios
        self.update_daily_active_users()
        
        # Actualizar distribución por género
        self.update_gender_stats()
        
        # Actualizar el pico de usuarios concurrentes
        self.update_peak_users()
        
        # Guardar cambios
        self.save_data()

    def update_peak_users(self):
        """Actualiza el pico de usuarios concurrentes."""
        # Calcular usuarios activos actualmente (en chat o esperando)
        active_users = len(self.active_chats) // 2  # Usuarios en chat
        waiting_users = sum(len(users) for users in self.waiting_users.values())  # Usuarios esperando
        if hasattr(self, 'gender_waiting_users'):
            waiting_users += sum(len(users) for users in self.gender_waiting_users.values())  # Usuarios en nuevas listas
        
        current_active = active_users + waiting_users
        
        # Actualizar el pico si es necesario
        if current_active > self.stats.get("peak_concurrent_users", 0):
            self.stats["peak_concurrent_users"] = current_active
            self.stats["peak_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            return True
        return False
    
    def update_gender_stats(self):
        """Actualiza las estadísticas de género basado en los usuarios actuales."""
        gender_stats = {"male": 0, "female": 0, "non_binary": 0, "unknown": 0}
        
        # Solo contar usuarios que están registrados actualmente
        for user_id, user_data in self.users.items():
            if isinstance(user_data, dict):
                gender = user_data.get("gender")
                if gender in gender_stats:
                    gender_stats[gender] += 1
                else:
                    gender_stats["unknown"] += 1
            else:
                logger.warning(f"User data for {user_id} is not a dictionary: {type(user_data)}")
                gender_stats["unknown"] += 1
        
        self.stats["gender_stats"] = gender_stats

    def set_user_gender(self, user_id, gender):
        """Establece el género del usuario."""
        # Normalize gender value
        if gender == "nonbinary":
            gender = "non_binary"
        
        if user_id in self.users:
            # Si el usuario ya estaba esperando, quitarlo de la lista anterior
            old_gender = self.users[user_id].get("gender")
            if old_gender in self.waiting_users and self.users[user_id].get("waiting_for_match", False):
                if user_id in self.waiting_users[old_gender]:
                    self.waiting_users[old_gender].remove(user_id)
            
            # Actualizar género
            self.users[user_id]["gender"] = gender
        else:
            self.users[user_id] = {
                "role": "user",
                "gender": gender,
                "joined_date": time.time(),
                "waiting_for_match": False,
                "paired_with": None
            }
            self.stats["total_users"] += 1
        
        self.update_gender_stats()
        self.save_data()

    def add_to_waiting(self, user_id, gender):
        """Añade usuario a la lista de espera correspondiente."""
        # Normalizar valor de género para la consistencia
        if gender == "nonbinary":
            gender = "non_binary"
            
        if user_id not in self.waiting_users[gender]:
            self.waiting_users[gender].append(user_id)
            self.users[user_id]["waiting_for_match"] = True
            self.save_data()
            return True
        return False

    def remove_from_waiting(self, user_id):
        """Elimina usuario de cualquier lista de espera."""
        for gender in self.waiting_users:
            if user_id in self.waiting_users[gender]:
                self.waiting_users[gender].remove(user_id)
                if user_id in self.users:
                    self.users[user_id]["waiting_for_match"] = False
                self.save_data()
                return True
        return False

    def create_chat(self, user_id1, user_id2):
        """Crea un chat entre dos usuarios."""
        self.active_chats[user_id1] = user_id2
        self.active_chats[user_id2] = user_id1
        
        if user_id1 in self.users:
            self.users[user_id1]["paired_with"] = user_id2
            self.users[user_id1]["waiting_for_match"] = False
        
        if user_id2 in self.users:
            self.users[user_id2]["paired_with"] = user_id1
            self.users[user_id2]["waiting_for_match"] = False
        
        self.stats["active_sessions"] += 1
        self.stats["total_chats"] += 1
        
        # Actualizar pico de usuarios
        current_sessions = len(self.active_chats) // 2
        if current_sessions > self.stats["peak_concurrent_users"]:
            self.stats["peak_concurrent_users"] = current_sessions
            self.stats["peak_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.save_data()

    def end_chat(self, user_id):
        """Finaliza un chat activo."""
        if user_id in self.active_chats:
            partner_id = self.active_chats[user_id]
            
            # Limpiar datos de chat para ambos usuarios
            if user_id in self.users:
                self.users[user_id]["paired_with"] = None
            
            if partner_id in self.users:
                self.users[partner_id]["paired_with"] = None
            
            # Eliminar del diccionario de chats activos
            del self.active_chats[user_id]
            del self.active_chats[partner_id]
            
            self.stats["active_sessions"] -= 1
            self.save_data()
            return partner_id
        
        return None

    def add_report(self, reporter_id, reported_id, reason, evidence_file_id=None):
        """Añade un nuevo reporte."""
        report = {
            "reporter_id": reporter_id,
            "reported_id": reported_id,
            "reason": reason,
            "evidence_file_id": evidence_file_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending"  # pending, reviewed, dismissed
        }
        self.reports.append(report)
        self.save_data()
        return len(self.reports) - 1  # Índice del reporte

    def is_admin(self, user_id):
        """Verifica si el usuario es admin."""
        return user_id in self.admins or user_id == self.super_admin_id

    def is_super_admin(self, user_id):
        """Verifica si el usuario es el superadministrador."""
        return user_id == self.super_admin_id

    def add_admin(self, user_id):
        """Añade un usuario como admin, si no lo es."""
        if user_id in self.admins or user_id == self.super_admin_id:
            return False
        self.admins.add(user_id)
        if user_id not in self.users:
            self.users[user_id] = {}
        self.users[user_id]["role"] = "admin"
        self.save_data()
        return True

    def remove_admin(self, user_id):
        """Elimina un admin, si existe."""
        if user_id not in self.admins:
            return False
        self.admins.remove(user_id)
        if user_id in self.users:
            if "role" in self.users[user_id]:
                self.users[user_id].pop("role", None)
        self.save_data()
        return True

    def ban_user(self, user_id):
        """Banea a un usuario."""
        # Evitar banear al superadmin
        if user_id == self.super_admin_id:
            return False
        if user_id not in self.users:
            self.users[user_id] = {}
        if self.users[user_id].get("banned", False):
            return False
        self.users[user_id]["banned"] = True
        self.save_data()
        return True

    def unban_user(self, user_id):
        """Desbanea a un usuario."""
        if user_id not in self.users:
            return False
        if not self.users[user_id].get("banned", False):
            return False
        self.users[user_id]["banned"] = False
        self.save_data()
        return True

    def get_user_info_by_id(self, user_id, bot=None):
        """Retorna información básica de un usuario dado."""
        if user_id not in self.users:
            return None
        info = {
            "user_id": user_id,
            "gender": self.users[user_id].get("gender", "Desconocido"),
            "role": self.users[user_id].get("role", "user"),
            "banned": self.users[user_id].get("banned", False)
        }
        return info

    def get_waiting_counts(self):
        """Devuelve el recuento de usuarios esperando por género."""
        # Inicializar contadores
        counts = {"male": 0, "female": 0, "non_binary": 0}
        
        # Contar usuarios en la lista de espera
        for gender, users in self.waiting_users.items():
            for user_id in users:
                if user_id in self.users and self.users[user_id]["gender"] in counts:
                    counts[self.users[user_id]["gender"]] += 1
        
        return counts

    def get_active_counts(self):
        """Obtiene conteo de usuarios activos por género."""
        gender_counts = {"male": 0, "female": 0, "non_binary": 0}
        
        # Contar usuarios únicos en chats activos
        counted_users = set()
        for user_id in self.active_chats.keys():
            if user_id not in counted_users and user_id in self.users:
                counted_users.add(user_id)
                gender = self.users[user_id].get("gender")
                if gender == "male" or gender == "female":
                    gender_counts[gender] += 1
                elif gender == "non_binary" or gender == "nonbinary":
                    gender_counts["non_binary"] += 1
                    # Actualizar para consistencia si se encuentra "nonbinary"
                    if gender == "nonbinary":
                        self.users[user_id]["gender"] = "non_binary"
        
        return gender_counts

    def update_message_stats(self, message_type):
        """Actualiza las estadísticas de mensajes."""
        self.stats["messages_sent"] += 1
        if message_type in self.stats["content_types"]:
            self.stats["content_types"][message_type] += 1
        self.save_data()

    def get_user_info_by_id(self, user_id, bot=None):
        """Obtiene información detallada de un usuario por su ID."""
        user_info = {
            "id": user_id,
            "exists": False,
            "telegram_info": {},
            "bot_data": {}
        }
        
        # Intentar obtener información de Telegram si se proporciona el bot
        if bot:
            try:
                user = bot.get_chat(user_id)
                user_info["telegram_info"] = {
                    "first_name": user.first_name,
                    "last_name": user.last_name if hasattr(user, "last_name") else None,
                    "username": user.username if hasattr(user, "username") else None,
                    "is_bot": user.is_bot if hasattr(user, "is_bot") else False,
                    "language_code": user.language_code if hasattr(user, "language_code") else None
                }
            except Exception as e:
                logger.error(f"Error al obtener información de Telegram para usuario {user_id}: {e}")
        
        # Verificar si el usuario existe en nuestra base de datos
        if user_id in self.users:
            user_info["exists"] = True
            user_info["bot_data"] = self.users[user_id].copy()
            
            # Añadir información adicional
            if user_id in self.stats["user_last_active"]:
                last_active = self.stats["user_last_active"][user_id]
                user_info["bot_data"]["last_active"] = last_active
                user_info["bot_data"]["last_active_formatted"] = datetime.fromtimestamp(last_active).strftime("%Y-%m-%d %H:%M:%S")
                user_info["bot_data"]["days_since_active"] = (time.time() - last_active) / 86400
            
            # Estado actual del usuario
            if user_id in self.active_chats:
                user_info["bot_data"]["current_state"] = "in_chat"
                user_info["bot_data"]["chatting_with"] = self.active_chats[user_id]
            else:
                for gender, users in self.waiting_users.items():
                    if user_id in users:
                        user_info["bot_data"]["current_state"] = f"waiting_for_match_{gender}"
                        break
                else:
                    user_info["bot_data"]["current_state"] = "idle"
            
            # Historial de reportes
            reports_as_reporter = [r for r in self.reports if r["reporter_id"] == user_id]
            reports_as_reported = [r for r in self.reports if r["reported_id"] == user_id]
            
            user_info["bot_data"]["reports_filed"] = len(reports_as_reporter)
            user_info["bot_data"]["times_reported"] = len(reports_as_reported)
        
        return user_info

    def check_spam(self, user_id):
        """
        Verifica si un usuario está enviando spam.
        Retorna (está_en_cooldown, segundos_restantes)
        """
        current_time = time.time()
        
        # Si no hay registro de spam para este usuario, crearlo
        if user_id not in self.spam_control:
            self.spam_control[user_id] = {
                "message_count": 1,
                "first_message_time": current_time,
                "cooldown_until": 0
            }
            return False, 0
        
        # Verificar si el usuario está en período de cooldown
        if self.spam_control[user_id]["cooldown_until"] > current_time:
            remaining = int(self.spam_control[user_id]["cooldown_until"] - current_time)
            return True, remaining
        
        # Si pasaron más de 60 segundos desde el primer mensaje, reiniciar contador
        time_window = 60  # ventana de 60 segundos
        if current_time - self.spam_control[user_id]["first_message_time"] > time_window:
            self.spam_control[user_id] = {
                "message_count": 1,
                "first_message_time": current_time,
                "cooldown_until": 0
            }
            return False, 0
        
        # Incrementar contador de mensajes
        self.spam_control[user_id]["message_count"] += 1
        
        # Si excede el límite, aplicar cooldown
        message_limit = 15
        if self.spam_control[user_id]["message_count"] > message_limit:
            cooldown_time = 20  # 20 segundos de cooldown (cambiado de 30 a 20)
            self.spam_control[user_id]["cooldown_until"] = current_time + cooldown_time
            self.spam_control[user_id]["message_count"] = 0
            return True, cooldown_time
        
        return False, 0

    def reset_spam_counter(self, user_id):
        """Reinicia el contador de spam para un usuario."""
        if user_id in self.spam_control:
            self.spam_control[user_id] = {
                "message_count": 0,
                "first_message_time": time.time(),
                "cooldown_until": 0
            }


# Funciones auxiliares
def format_time_difference(seconds):
    """Formatea una diferencia de tiempo en segundos a un formato legible."""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} día{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
    if seconds > 0 and len(parts) < 2:
        parts.append(f"{seconds} segundo{'s' if seconds != 1 else ''}")
    
    return ", ".join(parts)

def get_gender_emoji(gender):
    """Retorna emoji para género."""
    if gender == "male":
        return "👨"
    elif gender == "female":
        return "👩"
    else:  # non_binary
        return "🧑"

def get_gender_name(gender):
    """Retorna nombre del género en español."""
    if gender == "male":
        return "Hombre"
    elif gender == "female":
        return "Mujer"
    else:  # non_binary
        return "No Binario"