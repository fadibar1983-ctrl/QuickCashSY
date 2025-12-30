#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت QuickCashSY - الوساطة المالية الآمنة
الترخيص: MIT License
القسم 1 من 3
"""

import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ============ إعدادات البوت ============
BOT_TOKEN = "8559770088:AAGrruJ-Ij1Xidq6Nt6CZwWfNWAnNQIhklI"
ADMIN_ID = 8291006458
CHANNEL_LINK = "https://t.me/QuickCashSY"
CHANNEL_ID = "@QuickCashSY"
SUPPORT_USERNAME = "@QuickCashSY_Support"
OFFERS_PER_PAGE = 10
BOT_WALLET_ADDRESS = "TVGugqBG1hurAC5owpauA3yxYCFPY2zUS6"
COMMISSION_RATE = 0.001  # 0.1% عمولة وسيط
MIN_COMMISSION = 0.5  # دولار
FEE_OVER_1000 = 1.0  # دولار للصفقات فوق 1000 دولار

# ============ فئات طرق الدفع ============
PAYMENT_CATEGORIES = {
    "mobile_cash": {
        "name": "Syriatel/MTN Cash",
        "methods": ["سيريتل كاش", "ام تي ان كاش"]
    },
    "internal_transfers": {
        "name": "حوالات مالية داخلية",
        "methods": ["الهرم", "الهرم (دولار)", "شخاشيرو", "شخاشيرو (دولار)", "الفؤاد", "الفؤاد (دولار)", "القدموس"]
    },
    "sham_cash": {
        "name": "Sham Cash $ & s.p",
        "methods": ["شام كاش", "شام كاش (دولار)"]
    }
}

# ============ إعدادات التسجيل ============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ============ هياكل البيانات ============
class OfferState:
    def __init__(self, user_id):
        self.user_id = user_id
        self.offer_type = "بيع"
        self.price = None
        self.min_amount = None
        self.max_amount = None
        self.payment_methods = []
        self.waiting_for_payment_proof = False

class TransactionState:
    def __init__(self, user_id, offer_id, offer_type, seller_id, price, min_amount, max_amount, payment_methods):
        self.user_id = user_id
        self.offer_id = offer_id
        self.offer_type = offer_type
        self.seller_id = seller_id
        self.price = price
        self.min_amount = min_amount
        self.max_amount = max_amount
        self.selected_payment_methods = payment_methods
        self.selected_amount = None
        self.selected_payment_method = None
        self.confirmed = False

class OfferFilterState:
    def __init__(self):
        self.category = None
        self.offer_type = None
        self.sort_order = "newest"
        self.page = 0

# ============ متغيرات الحالة ============
user_states = {}
payment_verifications = {}
pending_offers = {}
offer_filters = {}
user_registration = {}
user_transactions = {}
editing_offers = {}
pending_approvals = {}

# ============ قاعدة البيانات ============
class DatabaseManager:
    def __init__(self):
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone_number TEXT,
            contact_info TEXT,
            join_date TEXT,
            referral_code TEXT UNIQUE,
            referral_count INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            reputation INTEGER DEFAULT 100,
            free_transactions INTEGER DEFAULT 1,
            paid_entry_fee INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            ban_date TEXT,
            total_transactions INTEGER DEFAULT 0,
            completed_transactions INTEGER DEFAULT 0,
            completion_rate REAL DEFAULT 0.0,
            user_level TEXT DEFAULT 'برونزي',
            transaction_value REAL DEFAULT 0.0,
            accepted_terms INTEGER DEFAULT 0,
            joined_channel INTEGER DEFAULT 0,
            registration_step TEXT DEFAULT 'start'
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            offer_type TEXT,
            min_amount REAL,
            max_amount REAL,
            price REAL,
            payment_method TEXT,
            status TEXT DEFAULT 'pending',
            admin_reviewed INTEGER DEFAULT 0,
            admin_id INTEGER,
            review_date TEXT,
            created_at TEXT,
            channel_message_id INTEGER DEFAULT 0,
            transaction_duration INTEGER DEFAULT 60,
            is_completed INTEGER DEFAULT 0,
            completed_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER,
            buyer_id INTEGER,
            seller_id INTEGER,
            amount REAL,
            price REAL,
            total_price REAL,
            payment_method TEXT,
            status TEXT DEFAULT 'pending_approval',
            admin_approved INTEGER DEFAULT 0,
            admin_id INTEGER,
            admin_approval_date TEXT,
            created_at TEXT,
            completed_at TEXT,
            buyer_confirmed INTEGER DEFAULT 0,
            seller_confirmed INTEGER DEFAULT 0,
            cancellation_reason TEXT,
            payment_proof TEXT,
            usdt_transaction_hash TEXT,
            commission REAL DEFAULT 0.0,
            commission_paid INTEGER DEFAULT 0,
            FOREIGN KEY (offer_id) REFERENCES offers (offer_id),
            FOREIGN KEY (buyer_id) REFERENCES users (user_id),
            FOREIGN KEY (seller_id) REFERENCES users (user_id)
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_type TEXT,
            user_id INTEGER,
            offer_id INTEGER,
            transaction_id INTEGER,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT
        )
        ''')
        
        # إضافة الأعمدة المفقودة
        columns_to_add = [
            ('users', 'phone_number', 'TEXT'),
            ('users', 'contact_info', 'TEXT'),
            ('users', 'accepted_terms', 'INTEGER DEFAULT 0'),
            ('users', 'joined_channel', 'INTEGER DEFAULT 0'),
            ('users', 'registration_step', 'TEXT DEFAULT "start"'),
            ('users', 'total_transactions', 'INTEGER DEFAULT 0'),
            ('users', 'completed_transactions', 'INTEGER DEFAULT 0'),
            ('users', 'completion_rate', 'REAL DEFAULT 0.0'),
            ('users', 'user_level', 'TEXT DEFAULT "برونزي"'),
            ('users', 'transaction_value', 'REAL DEFAULT 0.0'),
            ('offers', 'transaction_duration', 'INTEGER DEFAULT 60'),
            ('offers', 'is_completed', 'INTEGER DEFAULT 0'),
            ('offers', 'completed_date', 'TEXT'),
            ('transactions', 'payment_proof', 'TEXT'),
            ('transactions', 'usdt_transaction_hash', 'TEXT'),
            ('transactions', 'commission', 'REAL DEFAULT 0.0'),
            ('transactions', 'commission_paid', 'INTEGER DEFAULT 0'),
            ('transactions', 'status', 'TEXT DEFAULT "pending_approval"')
        ]
        
        for table, column, col_type in columns_to_add:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            except sqlite3.OperationalError:
                pass
        
        # فهارس لتحسين الأداء
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_user ON offers(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_read ON admin_notifications(is_read)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_buyer ON transactions(buyer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_seller ON transactions(seller_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_completed ON offers(is_completed)')
        
        conn.commit()
        conn.close()
        print("✅ تم تهيئة قاعدة البيانات")
    
    # ============ إدارة المستخدمين ============
    def is_user_banned(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT is_banned, ban_reason FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] == 1:
            return True, result[1]
        return False, None
    
    def is_user_registered(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT accepted_terms, joined_channel, phone_number FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            accepted_terms, joined_channel, phone_number = result
            return accepted_terms == 1 and joined_channel == 1 and phone_number is not None
        return False
    
    def get_user_registration_step(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT registration_step FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def update_user_registration_step(self, user_id, step):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, registration_step, join_date)
                VALUES (?, ?, ?)
            ''', (user_id, step, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        else:
            cursor.execute('UPDATE users SET registration_step = ? WHERE user_id = ?', (step, user_id))
        
        conn.commit()
        conn.close()
    
    def set_user_accepted_terms(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, accepted_terms, join_date, registration_step)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 1, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'channel_check'))
        else:
            cursor.execute('UPDATE users SET accepted_terms = 1, registration_step = "channel_check" WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    def set_user_joined_channel(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, joined_channel, join_date, registration_step)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 1, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'contact_registration'))
        else:
            cursor.execute('UPDATE users SET joined_channel = 1, registration_step = "contact_registration" WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    def save_user_contact_info(self, user_id, phone_number, contact_info):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, phone_number, contact_info, join_date, registration_step)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, phone_number, contact_info, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'completed'))
        else:
            cursor.execute('UPDATE users SET phone_number = ?, contact_info = ?, registration_step = "completed" WHERE user_id = ?', 
                          (phone_number, contact_info, user_id))
        
        conn.commit()
        conn.close()
    
    def ban_user(self, user_id, reason="مخالفة الشروط"):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, join_date, is_banned, ban_reason, ban_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 1, reason, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        else:
            cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, ban_date = ? WHERE user_id = ?', 
                          (reason, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
        
        conn.commit()
        conn.close()
        self.deactivate_user_offers(user_id)
    
    def unban_user(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, ban_date = NULL WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    def deactivate_user_offers(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE offers SET status = "expired" WHERE user_id = ? AND status IN ("active", "pending")', (user_id,))
        conn.commit()
        conn.close()
    
    def has_paid_entry_fee(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT paid_entry_fee FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result and result[0] == 1
    
    def set_paid_entry_fee(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, join_date, paid_entry_fee, registration_step)
                VALUES (?, ?, ?, ?)
            ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 1, 'completed'))
        else:
            cursor.execute('UPDATE users SET paid_entry_fee = 1 WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    def get_user_info(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, phone_number, contact_info, join_date, 
                   reputation, is_banned, ban_reason, total_transactions, completed_transactions, 
                   completion_rate, user_level, accepted_terms, joined_channel, registration_step
            FROM users WHERE user_id = ?
        ''', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    
    def get_all_users(self):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, phone_number, join_date, 
                   reputation, is_banned, total_transactions, completed_transactions, user_level,
                   accepted_terms, joined_channel, registration_step
            FROM users ORDER BY join_date DESC
        ''')
        users = cursor.fetchall()
        conn.close()
        return users
    
    # ============ إدارة العروض ============
    def add_offer(self, user_id, offer_type, min_amount, max_amount, price, payment_method):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, join_date, reputation, completion_rate, total_transactions, user_level, registration_step)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 100, 0.0, 0, 'جديد', 'completed'))
            print(f"✅ [DEBUG] تم إنشاء مستخدم جديد: {user_id}")
        
        cursor.execute('''
        INSERT INTO offers (user_id, offer_type, min_amount, max_amount, price, payment_method, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, offer_type, min_amount, max_amount, price, payment_method, 'pending', 
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        offer_id = cursor.lastrowid
        
        cursor.execute('''
        INSERT INTO admin_notifications (notification_type, user_id, offer_id, message, created_at)
        VALUES (?, ?, ?, ?, ?)
        ''', ('new_offer', user_id, offer_id, f'عرض جديد #{offer_id} ({offer_type}) ينتظر المراجعة', 
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        conn.commit()
        conn.close()
        print(f"✅ [DEBUG] تم إضافة عرض #{offer_id} للمستخدم {user_id}")
        return offer_id
    
    def update_offer(self, offer_id, min_amount=None, max_amount=None, price=None, payment_method=None):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if min_amount is not None:
            updates.append("min_amount = ?")
            params.append(min_amount)
        if max_amount is not None:
            updates.append("max_amount = ?")
            params.append(max_amount)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if payment_method is not None:
            updates.append("payment_method = ?")
            params.append(payment_method)
        
        if updates:
            query = f"UPDATE offers SET {', '.join(updates)} WHERE offer_id = ?"
            params.append(offer_id)
            cursor.execute(query, params)
            
            cursor.execute('''
            INSERT INTO admin_notifications (notification_type, offer_id, message, created_at)
            VALUES (?, ?, ?, ?)
            ''', ('offer_updated', offer_id, f'تم تحديث العرض #{offer_id}', 
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        conn.commit()
        conn.close()
        return True
    
    def delete_offer(self, offer_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id, channel_message_id FROM offers WHERE offer_id = ?', (offer_id,))
        offer = cursor.fetchone()
        
        if offer:
            user_id, channel_message_id = offer
            
            cursor.execute('DELETE FROM offers WHERE offer_id = ?', (offer_id,))
            
            cursor.execute('''
            INSERT INTO admin_notifications (notification_type, user_id, offer_id, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            ''', ('offer_deleted', user_id, offer_id, f'تم حذف العرض #{offer_id}', 
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            conn.commit()
            conn.close()
            return True, channel_message_id
        conn.close()
        return False, None
    
    def mark_offer_completed(self, offer_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE offers SET is_completed = 1, completed_date = ?, status = 'completed'
        WHERE offer_id = ?
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), offer_id))
        
        conn.commit()
        conn.close()
        return True
    
    def get_filtered_offers(self, offer_type, category_key=None, sort_order="newest", page=0):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        query = '''
            SELECT o.*, u.username, u.reputation, u.completion_rate, u.total_transactions, u.user_level
            FROM offers o LEFT JOIN users u ON o.user_id = u.user_id
            WHERE o.status = "active" AND o.offer_type = ? AND o.is_completed = 0
        '''
        params = [offer_type]
        
        if category_key and category_key in PAYMENT_CATEGORIES:
            category_methods = PAYMENT_CATEGORIES[category_key]["methods"]
            query += " AND ("
            conditions = []
            for method in category_methods:
                conditions.append(f"o.payment_method LIKE ?")
                params.append(f'%{method}%')
            query += " OR ".join(conditions) + ")"
        
        if sort_order == "price_asc":
            query += " ORDER BY o.price ASC"
        elif sort_order == "price_desc":
            query += " ORDER BY o.price DESC"
        else:
            query += " ORDER BY o.created_at DESC"
        
        query += " LIMIT ? OFFSET ?"
        params.extend([OFFERS_PER_PAGE, page * OFFERS_PER_PAGE])
        
        cursor.execute(query, params)
        offers = cursor.fetchall()
        
        count_query = 'SELECT COUNT(*) FROM offers o WHERE o.status = "active" AND o.offer_type = ? AND o.is_completed = 0'
        count_params = [offer_type]
        
        if category_key and category_key in PAYMENT_CATEGORIES:
            category_methods = PAYMENT_CATEGORIES[category_key]["methods"]
            count_query += " AND ("
            conditions = []
            for method in category_methods:
                conditions.append(f"o.payment_method LIKE ?")
                count_params.append(f'%{method}%')
            count_query += " OR ".join(conditions) + ")"
        
        cursor.execute(count_query, count_params)
        total_count = cursor.fetchone()[0]
        
        conn.close()
        return offers, total_count
    
    def get_pending_offers(self):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, u.username, u.reputation, u.completion_rate, u.total_transactions, u.user_level
            FROM offers o LEFT JOIN users u ON o.user_id = u.user_id
            WHERE o.status = "pending" ORDER BY o.created_at DESC
        ''')
        offers = cursor.fetchall()
        conn.close()
        return offers
    
    def get_active_offers(self, offer_type=None):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        if offer_type:
            cursor.execute('''
                SELECT o.*, u.username, u.reputation, u.completion_rate, u.total_transactions, u.user_level
                FROM offers o LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.status = "active" AND o.offer_type = ? AND o.is_completed = 0 ORDER BY o.created_at DESC
            ''', (offer_type,))
        else:
            cursor.execute('''
                SELECT o.*, u.username, u.reputation, u.completion_rate, u.total_transactions, u.user_level
                FROM offers o LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.status = "active" AND o.is_completed = 0 ORDER BY o.created_at DESC
            ''')
        
        offers = cursor.fetchall()
        conn.close()
        return offers
    
    def approve_offer(self, offer_id, admin_id, channel_message_id=0):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE offers SET status = "active", admin_reviewed = 1, admin_id = ?, review_date = ?, channel_message_id = ?
            WHERE offer_id = ?
        ''', (admin_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), channel_message_id, offer_id))
        conn.commit()
        conn.close()
    
    def reject_offer(self, offer_id, admin_id, reason="عدم المطابقة للشروط"):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE offers SET status = "rejected", admin_reviewed = 1, admin_id = ?, review_date = ?
            WHERE offer_id = ?
        ''', (admin_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), offer_id))
        conn.commit()
        conn.close()
        return reason
    
    def get_offer_by_id(self, offer_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, u.username, u.first_name, u.reputation, u.completion_rate, 
                   u.total_transactions, u.completed_transactions, u.user_level
            FROM offers o LEFT JOIN users u ON o.user_id = u.user_id
            WHERE o.offer_id = ?
        ''', (offer_id,))
        offer = cursor.fetchone()
        conn.close()
        return offer
    
    def get_user_offers(self, user_id, status=None, include_completed=False):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        query = 'SELECT * FROM offers WHERE user_id = ?'
        params = [user_id]
        
        if status and status != 'all':
            query += ' AND status = ?'
            params.append(status)
        
        if not include_completed:
            query += ' AND is_completed = 0'
        
        query += ' ORDER BY created_at DESC'
        
        cursor.execute(query, params)
        offers = cursor.fetchall()
        conn.close()
        return offers
    
    def get_user_pending_requests(self, user_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.*, o.offer_type, o.price
            FROM transactions t
            LEFT JOIN offers o ON t.offer_id = o.offer_id
            WHERE (t.buyer_id = ? OR t.seller_id = ?) 
            AND t.status IN ('pending_approval', 'active')
            ORDER BY t.created_at DESC
        ''', (user_id, user_id))
        
        transactions = cursor.fetchall()
        conn.close()
        return transactions
    
    # ============ إدارة المعاملات ============
    def add_transaction(self, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        # حساب العمولة
        commission = amount * COMMISSION_RATE
        if amount >= 1000:
            commission = max(commission, FEE_OVER_1000)
        else:
            commission = max(commission, MIN_COMMISSION)
        
        cursor.execute('''
        INSERT INTO transactions (offer_id, buyer_id, seller_id, amount, price, total_price, 
                                payment_method, status, created_at, commission)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, 'pending_approval',
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), commission))
        
        transaction_id = cursor.lastrowid
        
        cursor.execute('''
        INSERT INTO admin_notifications (notification_type, user_id, offer_id, transaction_id, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', ('new_transaction', buyer_id, offer_id, transaction_id, f'طلب معاملة جديدة #{transaction_id} من المستخدم {buyer_id}',
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        conn.commit()
        conn.close()
        return transaction_id
    
    def get_pending_transactions(self):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, u1.username as buyer_username, u2.username as seller_username, o.offer_type
            FROM transactions t
            LEFT JOIN users u1 ON t.buyer_id = u1.user_id
            LEFT JOIN users u2 ON t.seller_id = u2.user_id
            LEFT JOIN offers o ON t.offer_id = o.offer_id
            WHERE t.status = "pending_admin" ORDER BY t.created_at DESC
        ''')
        transactions = cursor.fetchall()
        conn.close()
        return transactions
    
    def get_pending_approval_transactions(self):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, u1.username as buyer_username, u2.username as seller_username, o.offer_type
            FROM transactions t
            LEFT JOIN users u1 ON t.buyer_id = u1.user_id
            LEFT JOIN users u2 ON t.seller_id = u2.user_id
            LEFT JOIN offers o ON t.offer_id = o.offer_id
            WHERE t.status = "pending_approval" ORDER BY t.created_at DESC
        ''')
        transactions = cursor.fetchall()
        conn.close()
        return transactions
    
    def approve_transaction(self, transaction_id, admin_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions SET status = "active", admin_approved = 1, admin_id = ?, admin_approval_date = ?
            WHERE transaction_id = ?
        ''', (admin_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), transaction_id))
        conn.commit()
        conn.close()
    
    def reject_transaction(self, transaction_id, admin_id, reason):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions SET status = "rejected", admin_approved = 0, admin_id = ?, 
            admin_approval_date = ?, cancellation_reason = ? WHERE transaction_id = ?
        ''', (admin_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reason, transaction_id))
        conn.commit()
        conn.close()
    
    def update_transaction_payment_proof(self, transaction_id, payment_proof):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions SET payment_proof = ? WHERE transaction_id = ?
        ''', (payment_proof, transaction_id))
        conn.commit()
        conn.close()
    
    def update_transaction_usdt_hash(self, transaction_id, usdt_hash):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions SET usdt_transaction_hash = ? WHERE transaction_id = ?
        ''', (usdt_hash, transaction_id))
        conn.commit()
        conn.close()
    
    def set_seller_approved(self, transaction_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions SET seller_confirmed = 1 WHERE transaction_id = ?
        ''', (transaction_id,))
        conn.commit()
        conn.close()
    
    def set_seller_rejected(self, transaction_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions SET status = "seller_rejected" WHERE transaction_id = ?
        ''', (transaction_id,))
        conn.commit()
        conn.close()
    
    def complete_transaction(self, transaction_id, usdt_hash=None):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        if usdt_hash:
            cursor.execute('UPDATE transactions SET status = "completed", completed_at = ?, usdt_transaction_hash = ?, commission_paid = 1 WHERE transaction_id = ?',
                          (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), usdt_hash, transaction_id))
        else:
            cursor.execute('UPDATE transactions SET status = "completed", completed_at = ? WHERE transaction_id = ?',
                          (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), transaction_id))
        
        cursor.execute('SELECT buyer_id, seller_id, amount, total_price, offer_id FROM transactions WHERE transaction_id = ?', (transaction_id,))
        transaction = cursor.fetchone()
        
        if transaction:
            buyer_id, seller_id, amount, total_price, offer_id = transaction
            
            cursor.execute('UPDATE users SET total_transactions = total_transactions + 1, completed_transactions = completed_transactions + 1, transaction_value = transaction_value + ? WHERE user_id = ?', 
                          (total_price, buyer_id))
            cursor.execute('UPDATE users SET total_transactions = total_transactions + 1, completed_transactions = completed_transactions + 1, transaction_value = transaction_value + ? WHERE user_id = ?', 
                          (total_price, seller_id))
            
            for user_id in [buyer_id, seller_id]:
                cursor.execute('SELECT total_transactions, completed_transactions FROM users WHERE user_id = ?', (user_id,))
                user_stats = cursor.fetchone()
                if user_stats:
                    total, completed = user_stats
                    completion_rate = (completed / total * 100) if total > 0 else 0
                    cursor.execute('UPDATE users SET completion_rate = ? WHERE user_id = ?', (completion_rate, user_id))
            
            cursor.execute('UPDATE offers SET is_completed = 1, completed_date = ? WHERE offer_id = ?',
                          (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), offer_id))
        
        conn.commit()
        conn.close()
    
    def cancel_user_transaction(self, user_id, transaction_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE transactions SET status = "cancelled_by_user", cancellation_reason = "ألغى المستخدم الطلب"
            WHERE transaction_id = ? AND (buyer_id = ? OR seller_id = ?)
        ''', (transaction_id, user_id, user_id))
        
        affected = cursor.rowcount
        
        conn.commit()
        conn.close()
        return affected > 0
    
    def get_transaction_by_id(self, transaction_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, u1.username as buyer_username, u1.first_name as buyer_name,
                   u2.username as seller_username, u2.first_name as seller_name,
                   o.offer_type, o.payment_method as offer_payment_methods
            FROM transactions t
            LEFT JOIN users u1 ON t.buyer_id = u1.user_id
            LEFT JOIN users u2 ON t.seller_id = u2.user_id
            LEFT JOIN offers o ON t.offer_id = o.offer_id
            WHERE t.transaction_id = ?
        ''', (transaction_id,))
        transaction = cursor.fetchone()
        conn.close()
        return transaction
    
    def get_user_transactions(self, user_id, status=None):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        if status:
            cursor.execute('''
                SELECT t.*, u.username as other_username, o.offer_type
                FROM transactions t
                LEFT JOIN users u ON (
                    CASE WHEN t.buyer_id = ? THEN t.seller_id ELSE t.buyer_id END
                ) = u.user_id
                LEFT JOIN offers o ON t.offer_id = o.offer_id
                WHERE (t.buyer_id = ? OR t.seller_id = ?) AND t.status = ?
                ORDER BY t.created_at DESC
            ''', (user_id, user_id, user_id, status))
        else:
            cursor.execute('''
                SELECT t.*, u.username as other_username, o.offer_type
                FROM transactions t
                LEFT JOIN users u ON (
                    CASE WHEN t.buyer_id = ? THEN t.seller_id ELSE t.buyer_id END
                ) = u.user_id
                LEFT JOIN offers o ON t.offer_id = o.offer_id
                WHERE (t.buyer_id = ? OR t.seller_id = ?)
                ORDER BY t.created_at DESC
            ''', (user_id, user_id, user_id))
        
        transactions = cursor.fetchall()
        conn.close()
        return transactions
    
    # ============ الإشعارات ============
    def get_unread_notifications_count(self):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM admin_notifications WHERE is_read = 0')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def mark_notification_read(self, notification_id):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE admin_notifications SET is_read = 1 WHERE id = ?', (notification_id,))
        conn.commit()
        conn.close()
    
    def add_notification(self, notification_type, user_id=None, offer_id=None, transaction_id=None, message=""):
        conn = sqlite3.connect('quickcash_users.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO admin_notifications (notification_type, user_id, offer_id, transaction_id, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (notification_type, user_id, offer_id, transaction_id, message, 
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        conn.commit()
        conn.close()

# ============ وظائف المساعدة ============
async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"خطأ في التحقق من عضوية القناة: {e}")
        return False

async def notify_admin_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, photo_id: str):
    try:
        user = update.effective_user
        user_info = f"@{user.username}" if user.username else f"{user.first_name} (ID: {user_id})"
        
        caption = f"""
🔄 **طلب تفعيل حساب جديد**

👤 **المستخدم:** {user_info}
🆔 **رقم المعرف:** {user_id}
📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ **يرجى مراجعة إثبات الدفع والتحقق منه.**

🔹 **خيارات:**"""
        
        keyboard = [
            [
                InlineKeyboardButton("✅ قبول وتفعيل", callback_data=f"approve_payment_{user_id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_payment_{user_id}")
            ]
        ]
        
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار للمسؤول: {e}")

async def notify_seller_new_request(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id: int, buyer_id: int, offer_id: int, amount: float, payment_method: str):
    try:
        db = DatabaseManager()
        
        buyer_info = db.get_user_info(buyer_id)
        transaction = db.get_transaction_by_id(transaction_id)
        offer = db.get_offer_by_id(offer_id)
        
        if not buyer_info or not transaction or not offer:
            return
        
        transaction_id, _, _, _, amount, price, total_price, payment_method, status, _, _, _, created_at, _, _, _, _, _, buyer_username, buyer_name, seller_username, seller_name, offer_type, _ = transaction
        offer_id, seller_id, offer_type, min_amount, max_amount, price, _, _, _, _, _, created_at, _, _, _, _, _, _, _, _ = offer
        
        buyer_name_display = f"@{buyer_username}" if buyer_username else buyer_name or f"المستخدم {buyer_id}"
        buyer_level = buyer_info[12] if len(buyer_info) > 12 else "جديد"
        buyer_completion_rate = buyer_info[11] if len(buyer_info) > 11 else 0.0
        buyer_total_transactions = buyer_info[9] if len(buyer_info) > 9 else 0
        buyer_reputation = buyer_info[6] if len(buyer_info) > 6 else 100.0
        
        level_emoji = {
            "ذهبى🥇": "🥇",
            "ذهبى": "🥇",
            "فضي🥈": "🥈",
            "فضي": "🥈",
            "برونزي🥉": "🥉",
            "برونزي": "🥉",
            "ألماسي💎": "💎",
            "جديد": "🆕"
        }.get(buyer_level, "🆕")
        
        message_text = f"""
🌟 **يوجد طلب جديد لزبون مهتم ب{offer_type} عرضك رقم : {offer_id} {'🛒' if offer_type == 'بيع' else '💰'}**

📋 **معلومات الطلب:**
🔗 **رقم عملية الربط :** {transaction_id}
🗂️ **النوع :** {'🔴 بيع 🔴' if offer_type == 'بيع' else '🔵 شراء 🔵'}
💰 **السعر :** {price:,.2f}
📦 **الكمية المطلوبة :** {amount}
💳 **طريقة الدفع :** {payment_method}

👤 **معلومات عن الزبون:**
🎖️ **المستوى :** {buyer_level}{level_emoji}
📈 **نسبة الإتمام:** {buyer_completion_rate:.1f}%  ({buyer_total_transactions} صفقات)
🧐 **السمعة :** ⭐️ {buyer_reputation:.1f}

🤔 **هل توافق على الطلب؟** 👇
"""
        
        keyboard = [
            [
                InlineKeyboardButton("✅ موافقة", callback_data=f"seller_approve_{transaction_id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"seller_reject_{transaction_id}")
            ]
        ]
        
        await context.bot.send_message(
            chat_id=seller_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار للبائع: {e}")

async def notify_admin_new_pending():
    """إرسال إشعار للمسؤول بوجود عروض أو معاملات منتظرة"""
    pass  # سيتم تنفيذها في القسم التالي

async def update_channel_offer_message(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id: int, completed=False):
    """تحديث رسالة العرض في القناة لتصبح مشطوبة"""
    try:
        db = DatabaseManager()
        offer = db.get_offer_by_id(offer_id)
        
        if not offer:
            return
        
        offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, _, _, _, _, _, _ = offer
        
        if not channel_message_id or channel_message_id == 0:
            return
        
        if completed:
            # تخطيط النص ليكون مشطوباً
            channel_message = f"""~~فرصة رقم : {offer_id}
{'🔴' if offer_type == 'بيع' else '🟢'} ~~التاجر يريد {offer_type} "USDT"~~
~~
~~💰 الكمية : من {min_amount} إلى {max_amount}~~
~~📊 سعر الصرف : {float(price):,.2f}~~
~~🏦 طرق الدفع : {payment_method}~~
~~⏳ مدة المعاملة : {transaction_duration} دقيقة~~
~~
~~معلومات عن التاجر :~~
~~👤 المستوى : {'🚫 محجوب'}~~
~~📈 نسبة الإتمام: {'🚫 محجوب'}~~
~~🧐 السمعة : ⭐️ {'🚫 محجوب'}~~
~~📉️ عمولة الوسيط: ({'🚫 محجوب'})~~

✅ **تم تنفيذ العرض** ✅
"""
        else:
            # نص العرض العادي
            channel_message = f"""فرصة رقم : {offer_id}
{'🔴' if offer_type == 'بيع' else '🟢'} التاجر يريد {offer_type} "USDT"
__
💰 الكمية : من {min_amount} إلى {max_amount}
📊 سعر الصرف : {float(price):,.2f}
🏦 طرق الدفع : {payment_method}
⏳ مدة المعاملة : {transaction_duration} دقيقة
__
معلومات عن التاجر :
👤 المستوى : {'🚫 محجوب'}
📈 نسبة الإتمام: {'🚫 محجوب'} 
🧐 السمعة : ⭐️ {'🚫 محجوب'}
📉️ عمولة الوسيط: ({'🚫 محجوب'})
"""
        
        keyboard = []
        
        if not completed:
            if offer_type == "بيع":
                keyboard.append([InlineKeyboardButton("🛒 شراء هذا العرض", url=f"https://t.me/Qcss_bot?start=offer_{offer_id}")])
                keyboard.append([InlineKeyboardButton("🔍 تصفح العروض الأخرى", url=f"https://t.me/Qcss_bot?start=browse")])
            else:
                keyboard.append([InlineKeyboardButton("💰 البيع لهذا الزبون", url=f"https://t.me/Qcss_bot?start=offer_{offer_id}")])
                keyboard.append([InlineKeyboardButton("🔍 تصفح العروض الأخرى", url=f"https://t.me/Qcss_bot?start=browse")])
        
        try:
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=channel_message_id,
                text=channel_message,
                reply_markup=InlineKeyboardMarkup(keyboard) if not completed else None,
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في تحديث رسالة القناة: {e}")
            
    except Exception as e:
        logging.error(f"خطأ في تحديث رسالة العرض في القناة: {e}")

# ============ نظام التسجيل ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(user_id)
    if is_banned:
        await update.message.reply_text(
            f"🚫 **تم حظر حسابك**\n\n"
            f"**السبب:** {ban_reason}\n\n"
            f"للاستفسار، تواصل مع الدعم: {SUPPORT_USERNAME}",
            parse_mode='Markdown'
        )
        return
    
    if db.is_user_registered(user_id):
        await show_main_interface(update, context, user)
        return
    
    registration_step = db.get_user_registration_step(user_id)
    
    if registration_step is None or registration_step == 'start':
        await show_terms_step(update, context)
        db.update_user_registration_step(user_id, 'terms')
    elif registration_step == 'terms':
        await show_terms_step(update, context)
    elif registration_step == 'channel_check':
        await show_channel_join_step(update, context)
    elif registration_step == 'contact_registration':
        await show_contact_registration_step(update, context)
    else:
        await show_terms_step(update, context)
        db.update_user_registration_step(user_id, 'terms')

async def show_terms_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    terms_text = """
📜 **مرحباً بك في QuickCashSY - منصة الوساطة المالية الآمنة**

✨ **قبل البدء، يرجى قراءة وقبول شروط الاستخدام التالية:**

**1. القبول بالشروط**
باستخدامك لـ **QuickCashSY**، فإنك تقر بأنك قرأت وفهمت ووافقت على الالتزام بجميع الشروط والأحكام.

**2. طبيعة الخدمة**
**QuickCashSY** هو بوت يقدم خدمة شخص لشخص (P2P) لعمليات بيع وشراء عملة الـ USDT.

**3. الالتزامات**
• استخدام الخدمة لأغراض قانونية فقط
• تقديم معلومات صحيحة ودقيقة
• احترام خصوصية الآخرين

**4. المسؤولية**
نحن وسيط بين الطرفين، ولن نكون مسؤولين عن أي نزاعات تنشأ بين المستخدمين.

**⚠️ لمواصلة استخدام البوت، يجب عليك:**
1. ✅ قبول الشروط والأحكام
2. 🔗 الانضمام لقناتنا الرسمية
3. 📱 تقديم معلومات الاتصال الخاصة بك

👇 **اضغط على الزر أدناه لقبول الشروط والمتابعة:**
    """
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            terms_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ أوافق على الشروط والأحكام", callback_data="accept_terms_step")
            ]]),
            parse_mode='Markdown'
        )
    elif update.message:
        await update.message.reply_text(
            terms_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ أوافق على الشروط والأحكام", callback_data="accept_terms_step")
            ]]),
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=terms_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ أوافق على الشروط والأحكام", callback_data="accept_terms_step")
            ]]),
            parse_mode='Markdown'
        )

async def show_channel_join_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_text = f"""
🔗 **الخطوة الثانية: الانضمام للقناة الرسمية**

📢 **للحفاظ على أمان المجتمع وتلقي آخر التحديثات، يجب انضمامك لقناتنا الرسمية:**

{CHANNEL_LINK}

**✨ فوائد الانضمام للقناة:**
• 📢 إشعارات فورية بالعروض الجديدة
• 🔔 تنبيهات بالصفقات المتاحة
• 📊 تحليلات وأسعار السوق
• 🎁 عروض حصرية للأعضاء

**📋 خطوات الانضمام:**
1. انضم للقناة عبر الرابط أعلاه
2. تأكد من تفعيل الإشعارات
3. اضغط على زر "✅ التحقق من الانضمام" أدناه

⚠️ **ملاحظة:** لن تتمكن من استخدام البوت دون الانضمام للقناة.
    """
    
    keyboard = [
        [InlineKeyboardButton("🔗 انضم للقناة", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ التحقق من الانضمام", callback_data="check_channel_membership")]
    ]
    
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(
            channel_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            channel_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def show_contact_registration_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_text = """
📱 **الخطوة الثالثة والأخيرة: مشاركة جهة الاتصال**

**🔒 لماذا نحتاج جهة اتصالك؟**
• ✅ تأكيد هويتك وحماية حسابك
• 🔄 التواصل في حالات الطوارئ
• 📞 تسهيل عملية الوساطة المالية

**⚡ كيفية التسجيل:**
اضغط على الزر أدناه **"📱 مشاركة جهة الاتصال"** لمشاركة معلومات الاتصال الخاصة بك تلقائياً.

⚠️ **سيتم استخدام هذه المعلومات للتواصل معك فقط ولن يتم مشاركتها مع طرف ثالث.**

📋 **المعلومات التي سيتم مشاركتها:**
• 📞 رقم هاتفك
• 👤 اسمك (إذا كان متوفراً)
• 🆔 معرفك في Telegram
    """
    
    keyboard = [
        [InlineKeyboardButton("📱 مشاركة جهة الاتصال", callback_data="share_contact")],
        [InlineKeyboardButton("🏠 إلغاء والعودة للبداية", callback_data="back_to_main")]
    ]
    
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(
            contact_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            contact_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def show_main_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    user_name = f"@{user.username}" if user.username else user.first_name
    
    welcome_text = f"""
🌟 **مرحباً بعودتك {user_name} إلى مجتمع QuickCashSY** 🌟

💎 **منصتك الآمنة للبيع والشراء**

✨ **ماذا يمكن أن نقوم به سوياً؟**
🚀 انشر عرضك الخاص للبيع والشراء
💫 تصفح العروض المتاحة واستفد من الفرص
📈 إدارة معاملاتك بذكاء وأكثر كفاءة

💰 **ابدأ معاملاتك واختر ما يناسبك من الخيارات المتاحة التالية:**
    """
    
    # ترتيب الأزرار بطريقة أجمل
    keyboard = [
        [
            InlineKeyboardButton("🛒 تصفح العروض", callback_data="browse_offers"),
            InlineKeyboardButton("💎 إنشاء عرض", callback_data="create_offer")
        ],
        [
            InlineKeyboardButton("📁 ملفي الشخصي", callback_data="my_profile"),
            InlineKeyboardButton("📊 إدارة عروضي", callback_data="my_offers")
        ],
        [
            InlineKeyboardButton("🔄 طلباتي", callback_data="my_requests"),
            InlineKeyboardButton("🔔 التنبيهات", callback_data="notifications")
        ],
        [
            InlineKeyboardButton("❓ الدعم", callback_data="support"),
            InlineKeyboardButton("📜 الشروط", callback_data="terms")
        ]
    ]
    
    if user.id == ADMIN_ID:
        keyboard.insert(0, [InlineKeyboardButton("🛠️ لوحة التحكم", callback_data="admin_panel")])
    
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def accept_terms_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(user_id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer("✅ تم قبول الشروط والأحكام", show_alert=True)
    db.set_user_accepted_terms(user_id)
    await show_channel_join_step(update, context)

async def check_channel_membership_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(user_id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer("⏳ جاري التحقق...")
    is_member = await check_channel_membership(update, context, user_id)
    
    if is_member:
        db.set_user_joined_channel(user_id)
        await show_contact_registration_step(update, context)
    else:
        await query.edit_message_text(
            "❌ **لم يتم العثور على عضويتك في القناة**\n\n"
            f"⚠️ **يرجى الانضمام للقناة أولاً:** {CHANNEL_LINK}\n\n"
            "🔍 **بعد الانضمام، اضغط على زر التحقق مرة أخرى**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 انضم للقناة", url=CHANNEL_LINK)],
                [InlineKeyboardButton("✅ التحقق من الانضمام", callback_data="check_channel_membership")]
            ]),
            parse_mode='Markdown'
        )

# ============ معالجة الرسائل النصية ============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text if update.message.text else ""
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(user_id)
    if is_banned and user_id != ADMIN_ID:
        await update.message.reply_text(
            f"🚫 **تم حظر حسابك**\n\n"
            f"**السبب:** {ban_reason}\n\n"
            f"للاستفسار، تواصل مع الدعم: {SUPPORT_USERNAME}",
            parse_mode='Markdown'
        )
        return
    
    # معالجة جهة الاتصال المرسلة
    if update.message.contact:
        await handle_contact_received(update, context)
        return
    
    # معالجة تعديل العروض
    if user_id in editing_offers:
        await handle_offer_editing(update, context, message_text)
        return
    
    if 'awaiting_contact_info' in context.user_data and context.user_data['awaiting_contact_info']:
        contact_info = message_text.strip()
        
        if len(contact_info) < 5:
            await update.message.reply_text(
                "⚠️ **الرجاء إدخال معلومات اتصال صحيحة**\n\n"
                "مثال: `0991234567 - @username`\n"
                "أو: `+963991234567 - 0991234567`",
                parse_mode='Markdown'
            )
            return
        
        parts = contact_info.split('-')
        phone_number = parts[0].strip()
        additional_info = parts[1].strip() if len(parts) > 1 else ""
        
        db.save_user_contact_info(user_id, phone_number, contact_info)
        del context.user_data['awaiting_contact_info']
        
        await update.message.reply_text(
            "🎉 **تم تسجيل معلوماتك بنجاح!**\n\n"
            "✅ **أكملت جميع خطوات التسجيل**\n"
            "🔓 **يمكنك الآن استخدام جميع مزايا البوت**\n\n"
            "👇 **من الواجهة الرئيسية:**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 الانتقال للواجهة الرئيسية", callback_data="back_to_main")
            ]]),
            parse_mode='Markdown'
        )
        return
    
    if update.message.photo and 'waiting_payment_proof' in context.user_data and context.user_data['waiting_payment_proof']:
        photo = update.message.photo[-1]
        
        payment_verifications[user_id] = {
            'photo_id': photo.file_id,
            'user_id': user_id,
            'username': update.effective_user.username,
            'first_name': update.effective_user.first_name,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        await update.message.reply_text(
            "✅ **تم استلام إثبات الدفع بنجاح!**\n\n"
            "📋 **سيتم مراجعة طلبك من قبل الإدارة خلال 24 ساعة.**\n"
            "🔔 **سيتم إعلامك عند تفعيل حسابك.**\n\n"
            "شكراً لصبرك وتعاونك! ✨",
            parse_mode='Markdown'
        )
        
        await notify_admin_payment_proof(update, context, user_id, photo.file_id)
        context.user_data['waiting_payment_proof'] = False
        return
    
    if user_id in user_transactions and context.user_data.get('awaiting_transaction_amount', False):
        try:
            amount = float(message_text)
            transaction_state = user_transactions[user_id]
            
            if amount < transaction_state.min_amount or amount > transaction_state.max_amount:
                await update.message.reply_text(
                    f"⚠️ **الرجاء إدخال كمية صحيحة**\n\n"
                    f"📊 **نطاق الكمية المقبول:** {transaction_state.min_amount} - {transaction_state.max_amount} USDT\n\n"
                    f"💡 **أدخل كمية صحيحة ضمن النطاق أعلاه:**",
                    parse_mode='Markdown'
                )
                return
            
            transaction_state.selected_amount = amount
            context.user_data['awaiting_transaction_amount'] = False
            await ask_payment_method(update, context, transaction_state)
            
        except ValueError:
            await update.message.reply_text(
                "⚠️ **الرجاء إدخال رقم صحيح أو عشري صحيح**\n\n"
                "💡 **مثال:** `10.5` أو `100`",
                parse_mode='Markdown'
            )
    
    elif user_id == ADMIN_ID:
        await handle_admin_messages(update, context, message_text)
    
    elif user_id in user_states:
        await handle_offer_creation(update, context, message_text)

async def handle_offer_editing(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """معالجة عملية تعديل العرض"""
    user_id = update.effective_user.id
    editing_state = editing_offers[user_id]
    
    if editing_state['step'] == 'awaiting_price':
        try:
            price = float(message_text)
            if price <= 0:
                await update.message.reply_text("⚠️ الرجاء إدخال سعر صحيح أكبر من الصفر")
                return
            
            editing_state['price'] = price
            editing_state['step'] = 'awaiting_min_amount'
            
            await update.message.reply_text(
                f"""✅ **تم حفظ السعر الجديد: {price:,.2f}**

💡 **الآن أدخل الحد الأدنى الجديد للعرض 📉:**

(يجب أن يكون الحد الأدنى أقل من الحد الأقصى)""",
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح أو عشري")
    
    elif editing_state['step'] == 'awaiting_min_amount':
        try:
            min_amount = float(message_text)
            if min_amount <= 0:
                await update.message.reply_text("⚠️ الرجاء إدخال كمية صحيحة أكبر من الصفر")
                return
            
            editing_state['min_amount'] = min_amount
            editing_state['step'] = 'awaiting_max_amount'
            
            await update.message.reply_text(
                f"""✅ **تم حفظ الحد الأدنى الجديد: {min_amount}**

💡 **الآن أدخل الحد الأقصى الجديد للعرض 📈:**

(يجب أن يكون الحد الأقصى أكبر من الحد الأدنى {min_amount})""",
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح أو عشري")
    
    elif editing_state['step'] == 'awaiting_max_amount':
        try:
            max_amount = float(message_text)
            if max_amount <= editing_state['min_amount']:
                await update.message.reply_text(f"⚠️ يجب أن يكون الحد الأقصى أكبر من الحد الأدنى ({editing_state['min_amount']})")
                return
            
            editing_state['max_amount'] = max_amount
            editing_state['step'] = 'awaiting_payment_methods'
            
            await show_edit_payment_methods(update, context)
            
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح أو عشري")

# ============ معالجة جهة الاتصال المستلمة ============
async def handle_contact_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    contact = update.message.contact
    
    db = DatabaseManager()
    
    registration_step = db.get_user_registration_step(user_id)
    if registration_step != 'contact_registration':
        await update.message.reply_text(
            "⚠️ **لم تصل بعد لمرحلة تسجيل جهة الاتصال**\n\n"
            "🔙 **يرجى البدء من البداية:**",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return
    
    phone_number = contact.phone_number
    contact_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
    contact_info = f"{phone_number} - {contact_name}"
    
    db.save_user_contact_info(user_id, phone_number, contact_info)
    
    await update.message.reply_text(
        "✅ **جاري معالجة معلوماتك...**",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    
    await asyncio.sleep(0.5)
    
    success_message = await update.message.reply_text(
        "🎉 **تم تسجيل جهة اتصالك بنجاح!**\n\n"
        "✅ **أكملت جميع خطوات التسجيل**\n"
        "🔓 **يمكنك الآن استخدام جميع مزايا البوت**\n\n"
        "👇 **من الواجهة الرئيسية:**",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 الانتقال للواجهة الرئيسية", callback_data="back_to_main")
        ]]),
        parse_mode='Markdown'
    )
    
    if 'contact_request_message_id' in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=user_id,
                message_id=context.user_data['contact_request_message_id']
            )
            del context.user_data['contact_request_message_id']
        except Exception as e:
            logging.error(f"خطأ في حذف رسالة طلب جهة الاتصال: {e}")
    
    await send_contact_registration_complete(update, context, user_id)

async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    
    if 'awaiting_reject_reason' in context.user_data and context.user_data['awaiting_reject_reason']:
        reason = message_text
        offer_id = context.user_data['rejecting_offer_id']
        
        db = DatabaseManager()
        db.reject_offer(offer_id, ADMIN_ID, reason)
        
        offer = db.get_offer_by_id(offer_id)
        if offer:
            offer_user_id = offer[1]
            try:
                await context.bot.send_message(
                    chat_id=offer_user_id,
                    text=f"""❌ **تم رفض عرضك**

📝 **عرض #{offer_id} تم رفضه من قبل الإدارة**

🔍 **سبب الرفض:** {reason}

💡 **نصائح:**
• تأكد من اتباع شروط الاستخدام
• تحقق من صحة المعلومات المقدمة
• يمكنك إنشاء عرض جديد بعد التصحيح

🏠 **من الواجهة الرئيسية:**""",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                    ]),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"خطأ في إرسال إشعار للمستخدم: {e}")
        
        await update.message.reply_text(
            f"✅ **تم رفض العرض #{offer_id} بنجاح**\n"
            f"**السبب:** {reason}",
            parse_mode='Markdown'
        )
        
        del context.user_data['awaiting_reject_reason']
        del context.user_data['rejecting_offer_id']
        
        keyboard = [[InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]]
        await update.message.reply_text(
            "🔙 **العودة للوحة التحكم:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    elif 'awaiting_ban_reason' in context.user_data and context.user_data['awaiting_ban_reason']:
        reason = message_text
        ban_user_id = context.user_data['banning_user_id']
        
        db = DatabaseManager()
        db.ban_user(ban_user_id, reason)
        
        try:
            await context.bot.send_message(
                chat_id=ban_user_id,
                text=f"""🚫 **تم حظر حسابك**

📝 **تم حظر حسابك من قبل إدارة QuickCashSY**

🔍 **سبب الحظر:** {reason}

⚠️ **لا يمكنك استخدام خدمات البوت أثناء الحظر**

📞 **للاستفسار أو الطعن في القرار، تواصل مع الدعم:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 الدعم الفني", url=f"tg://resolve?domain={SUPPORT_USERNAME[1:]}")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال إشعار للمستخدم المحظور: {e}")
        
        await update.message.reply_text(
            f"✅ **تم حظر المستخدم {ban_user_id} بنجاح**\n"
            f"**السبب:** {reason}",
            parse_mode='Markdown'
        )
        
        del context.user_data['awaiting_ban_reason']
        del context.user_data['banning_user_id']
        
        keyboard = [
            [InlineKeyboardButton("🔙 العودة لإدارة المستخدم", callback_data=f"admin_manage_user_{ban_user_id}")],
            [InlineKeyboardButton("🏠 لوحة التحكم", callback_data="admin_panel")]
        ]
        await update.message.reply_text(
            "🔙 **العودة:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    elif 'awaiting_transaction_reject_reason' in context.user_data and context.user_data['awaiting_transaction_reject_reason']:
        reason = message_text
        transaction_id = context.user_data['rejecting_transaction_id']
        
        db = DatabaseManager()
        db.reject_transaction(transaction_id, ADMIN_ID, reason)
        
        transaction = db.get_transaction_by_id(transaction_id)
        if transaction:
            buyer_id = transaction[2]
            try:
                await context.bot.send_message(
                    chat_id=buyer_id,
                    text=f"""❌ **تم رفض طلب المعاملة**

📝 **طلب المعاملة #{transaction_id} تم رفضه من قبل الإدارة**

🔍 **سبب الرفض:** {reason}

💡 **نصائح:**
• تأكد من صحة المعلومات المقدمة
• يمكنك تقديم طلب جديد بعد التصحيح

🏠 **من الواجهة الرئيسية:**""",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                    ]),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"خطأ في إرسال إشعار للمستخدم: {e}")
        
        await update.message.reply_text(
            f"✅ **تم رفض المعاملة #{transaction_id} بنجاح**\n"
            f"**السبب:** {reason}",
            parse_mode='Markdown'
        )
        
        del context.user_data['awaiting_transaction_reject_reason']
        del context.user_data['rejecting_transaction_id']
        await admin_review_transactions(update, context)
        return
    
    elif 'awaiting_admin_message' in context.user_data and context.user_data['awaiting_admin_message']:
        message = message_text
        target_user_id = context.user_data['messaging_user_id']
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"""📨 **رسالة من إدارة QuickCashSY**

{message}

🔚 **نهاية الرسالة**""",
                parse_mode='Markdown'
            )
            
            await update.message.reply_text(
                f"✅ **تم إرسال الرسالة بنجاح للمستخدم {target_user_id}**",
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ **فشل إرسال الرسالة للمستخدم {target_user_id}**\n"
                f"الخطأ: {str(e)}",
                parse_mode='Markdown'
            )
        
        del context.user_data['awaiting_admin_message']
        del context.user_data['messaging_user_id']
        
        keyboard = [
            [InlineKeyboardButton("🔙 العودة لإدارة المستخدم", callback_data=f"admin_manage_user_{target_user_id}")],
            [InlineKeyboardButton("🏠 لوحة التحكم", callback_data="admin_panel")]
        ]
        await update.message.reply_text(
            "🔙 **العودة:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    elif 'awaiting_broadcast_message' in context.user_data and context.user_data['awaiting_broadcast_message']:
        broadcast_message = message_text
        
        db = DatabaseManager()
        all_users = db.get_all_users()
        
        success_count = 0
        fail_count = 0
        
        await update.message.reply_text(
            "📢 **جاري إرسال رسالة البث للمستخدمين...**\n"
            "⏳ قد تستغرق العملية بعض الوقت...",
            parse_mode='Markdown'
        )
        
        for user in all_users:
            try:
                if user[5] == 1:
                    continue
                
                await context.bot.send_message(
                    chat_id=user[0],
                    text=f"""📢 **إشعار عام من إدارة QuickCashSY**

{broadcast_message}

🔚 **نهاية الرسالة**""",
                    parse_mode='Markdown'
                )
                success_count += 1
                await asyncio.sleep(0.1)
                
            except Exception as e:
                fail_count += 1
                logging.error(f"خطأ في إرسال بث للمستخدم {user[0]}: {e}")
        
        await update.message.reply_text(
            f"✅ **تم إكمال عملية البث**\n\n"
            f"📊 **النتائج:**\n"
            f"• ✅ تم الإرسال بنجاح: {success_count}\n"
            f"• ❌ فشل الإرسال: {fail_count}\n\n"
            f"📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )
        
        del context.user_data['awaiting_broadcast_message']
        
        keyboard = [[InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]]
        await update.message.reply_text(
            "🔙 **العودة للوحة التحكم:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

async def handle_offer_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    state = user_states[user_id]
    
    if 'awaiting_price' in context.user_data and context.user_data['awaiting_price']:
        try:
            price = float(message_text)
            if price <= 0:
                await update.message.reply_text("⚠️ الرجاء إدخال سعر صحيح أكبر من الصفر")
                return
            
            state.price = price
            context.user_data['awaiting_price'] = False
            context.user_data['awaiting_min_amount'] = True
            
            offer_type_emoji = "🔴 بيع 🔴" if state.offer_type == "بيع" else "🔵 شراء 🔵"
            
            await update.message.reply_text(
                f"""📊 **نوع العرض : {offer_type_emoji}**
💰 **السعر :** {price:,.2f} ليرة/USDT

💡 **نصائح:** 
• حدد كمية مناسبة لرأس مالك 
• اختر كمية تناسب قدراتك المالية 
• كمية أكبر تعني فرص تنفيذ أسرع 

🔢 **ادخل أقل كمية تقبل {'بيعها' if state.offer_type == 'بيع' else 'شراءها'} 📉:**""",
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح أو عشري")
    
    elif 'awaiting_min_amount' in context.user_data and context.user_data['awaiting_min_amount']:
        try:
            min_amount = float(message_text)
            if min_amount <= 0:
                await update.message.reply_text("⚠️ الرجاء إدخال كمية صحيحة أكبر من الصفر")
                return
            
            state.min_amount = min_amount
            context.user_data['awaiting_min_amount'] = False
            context.user_data['awaiting_max_amount'] = True
            
            offer_type_emoji = "🔴 بيع 🔴" if state.offer_type == "بيع" else "🔵 شراء 🔵"
            
            await update.message.reply_text(
                f"""📊 **نوع العرض : {offer_type_emoji}**
💰 **السعر :** {state.price:,.2f}
🔢 **الحد الأدنى :** {min_amount} USDT

💡 **نصائح:** 
• اختر حد أقصى يتناسب مع قدراتك 
• كمية أكبر تعني فرص تنفيذ أفضل 
• تأكد من توفر السيولة المناسبة 

🔢 **ادخل أعلى كمية تستطيع {'بيعها' if state.offer_type == 'بيع' else 'شراءها'} 📉:**""",
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح أو عشري")
    
    elif 'awaiting_max_amount' in context.user_data and context.user_data['awaiting_max_amount']:
        try:
            max_amount = float(message_text)
            if max_amount <= state.min_amount:
                await update.message.reply_text(f"⚠️ يجب أن يكون الحد الأقصى أكبر من الحد الأدنى ({state.min_amount})")
                return
            
            state.max_amount = max_amount
            context.user_data['awaiting_max_amount'] = False
            await show_payment_methods(update, context)
            
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح أو عشري")

async def ask_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_state):
    user_id = update.effective_user.id
    total_price = transaction_state.selected_amount * transaction_state.price
    payment_methods = transaction_state.selected_payment_methods
    
    payment_text = "💳 **اختر طريقة الدفع المناسبة**\n\n"
    payment_text += f"""💰 **تفاصيل الطلب:**
• **الكمية:** {transaction_state.selected_amount} USDT
• **السعر:** {transaction_state.price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة

👇 **طرق الدفع المتاحة:**\n"""
    
    payment_buttons = []
    for i, method in enumerate(payment_methods):
        payment_text += f"**{i+1}. {method}**\n"
        payment_buttons.append([InlineKeyboardButton(f"✅ {method}", callback_data=f"select_payment_{method}")])
    
    payment_text += "\n📋 **اختر طريقة واحدة فقط:**"
    payment_buttons.append([InlineKeyboardButton("❌ إلغاء العملية", callback_data="cancel_transaction")])
    
    await update.message.reply_text(
        payment_text,
        reply_markup=InlineKeyboardMarkup(payment_buttons),
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_payment_method'] = True

# ============ معالجة أوامر start مع باراميترات ============
async def handle_start_with_params(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(user.id)
    if is_banned:
        await update.message.reply_text(
            f"🚫 **تم حظر حسابك**\n\n"
            f"**السبب:** {ban_reason}\n\n"
            f"للاستفسار، تواصل مع الدعم: {SUPPORT_USERNAME}",
            parse_mode='Markdown'
        )
        return
    
    if db.is_user_registered(user.id):
        if context.args:
            param = context.args[0]
            
            if param.startswith("offer_"):
                offer_id = param.split("_")[1]
                await show_offer_details(update, context, offer_id)
                return
            elif param in ["browse", "sell", "buy"]:
                await browse_offers_from_start(update, context)
                return
        
        await show_main_interface(update, context, user)
    else:
        await start(update, context)

# ============ إدارة العروض (الميزة الجديدة) ============
async def my_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    db = DatabaseManager()
    
    user_offers = db.get_user_offers(user_id, include_completed=True)
    active_offers = [offer for offer in user_offers if offer[7] == 'active' and offer[14] == 0]
    pending_offers = [offer for offer in user_offers if offer[7] == 'pending']
    completed_offers = [offer for offer in user_offers if offer[14] == 1]
    
    offers_text = f"""
📊 **إدارة عروضي**

📈 **إحصائيات عروضك:**
├ ✅ **النشطة:** {len(active_offers)}
├ ⏳ **بانتظار المراجعة:** {len(pending_offers)}
├ 🏁 **المكتملة:** {len(completed_offers)}
└ 📋 **الإجمالي:** {len(user_offers)}

🔧 **اختر نوع العروض التي تريد إدارتها:**
"""
    
    keyboard = [
        [InlineKeyboardButton("✅ العروض النشطة", callback_data="my_active_offers")],
        [InlineKeyboardButton("⏳ العروض المنتظرة", callback_data="my_pending_offers")],
        [InlineKeyboardButton("🏁 العروض المكتملة", callback_data="my_completed_offers")],
        [InlineKeyboardButton("📋 جميع العروض", callback_data="my_all_offers")],
        [InlineKeyboardButton("🏠 العودة للواجهة الرئيسية", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        offers_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_user_offers_list(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_type="active"):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    
    if offer_type == "active":
        offers = db.get_user_offers(user_id, status='active')
        title = "✅ **العروض النشطة**"
    elif offer_type == "pending":
        offers = db.get_user_offers(user_id, status='pending')
        title = "⏳ **العروض المنتظرة**"
    elif offer_type == "completed":
        offers = db.get_user_offers(user_id, include_completed=True)
        offers = [offer for offer in offers if offer[14] == 1]
        title = "🏁 **العروض المكتملة**"
    else:
        offers = db.get_user_offers(user_id, include_completed=True)
        title = "📋 **جميع العروض**"
    
    if not offers:
        offers_text = f"""
{title}

📭 **لا توجد عروض {offer_type} حالياً**
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 رجوع لإدارة العروض", callback_data="my_offers")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
        ]
        
        await query.edit_message_text(
            offers_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    offers_text = f"""
{title}

📊 **عدد العروض:** {len(offers)}

👇 **اختر العرض الذي تريد إدارته:**
"""
    
    keyboard = []
    
    for offer in offers[:10]:
        offer_id = offer[0]
        offer_type_arabic = offer[2]
        price = offer[5]
        min_amount = offer[3]
        max_amount = offer[4]
        status = offer[7]
        is_completed = offer[14] if len(offer) > 14 else 0
        
        status_emoji = "✅" if status == 'active' and is_completed == 0 else "⏳" if status == 'pending' else "🏁"
        
        offer_button_text = f"{status_emoji} عرض #{offer_id} ({offer_type_arabic}) - {price:,.2f}"
        keyboard.append([InlineKeyboardButton(offer_button_text, callback_data=f"manage_offer_{offer_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("🔙 رجوع لإدارة العروض", callback_data="my_offers")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
    ])
    
    await query.edit_message_text(
        offers_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def manage_specific_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    offer_id, offer_user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, _, _, _, _, _, _ = offer
    
    if offer_user_id != user_id:
        await query.answer("⚠️ ليس لديك صلاحية إدارة هذا العرض", show_alert=True)
        return
    
    is_completed = offer[14] if len(offer) > 14 else 0
    
    offer_details = f"""
📋 **تفاصيل العرض #{offer_id}**

📊 **معلومات العرض:**
├ 📝 **النوع:** {offer_type}
├ 💰 **السعر:** {price:,.2f} ليرة/USDT
├ 📦 **الكمية:** {min_amount} - {max_amount} USDT
├ ⏳ **المدة:** {transaction_duration} دقيقة
├ 📅 **تاريخ الإنشاء:** {created_at[:16]}
├ ✅ **الحالة:** {status}
└ 🏁 **مكتمل:** {'نعم' if is_completed == 1 else 'لا'}

💳 **طرق الدفع المتاحة:**
{payment_method}

🔧 **خيارات الإدارة:**
"""
    
    keyboard = []
    
    if status == 'active' and is_completed == 0:
        keyboard.append([InlineKeyboardButton("✏️ تعديل العرض", callback_data=f"edit_offer_{offer_id}")])
        keyboard.append([InlineKeyboardButton("🗑️ حذف العرض", callback_data=f"delete_offer_{offer_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("📋 طلبات هذا العرض", callback_data=f"offer_requests_{offer_id}")],
        [
            InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="my_active_offers"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")
        ]
    ])
    
    await query.edit_message_text(
        offer_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def start_edit_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    offer_id, offer_user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, _, _, _, _, _, _ = offer
    
    if offer_user_id != user_id:
        await query.answer("⚠️ ليس لديك صلاحية تعديل هذا العرض", show_alert=True)
        return
    
    if status != 'active':
        await query.answer("⚠️ لا يمكن تعديل العرض غير النشط", show_alert=True)
        return
    
    editing_offers[user_id] = {
        'offer_id': offer_id,
        'offer_type': offer_type,
        'price': price,
        'min_amount': min_amount,
        'max_amount': max_amount,
        'payment_methods': payment_method.split(','),
        'step': 'awaiting_price',
        'original_payment_methods': payment_method.split(',')
    }
    
    await query.edit_message_text(
        f"""✏️ **تعديل العرض #{offer_id}**

📋 **أنت الآن في وضع تعديل العرض.**

💡 **أدخل السعر الجديد للعرض:**
(السعر الحالي: {price:,.2f} ليرة/USDT)

✏️ **أدخل السعر الجديد الآن:**""",
        parse_mode='Markdown'
    )

async def show_edit_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in editing_offers:
        await update.message.reply_text("❌ انتهت جلسة التعديل. يرجى البدء من جديد.")
        return
    
    editing_state = editing_offers[user_id]
    
    payment_methods_text = f"""✅ **تفاصيل العرض المعدل:**

📊 **نوع العرض :** {editing_state['offer_type']}
💰 **السعر الجديد :** {editing_state['price']:,.2f} ليرة/USDT
🔢 **الحد الأدنى الجديد :** {editing_state['min_amount']} USDT
🔢 **الحد الأقصى الجديد :** {editing_state['max_amount']} USDT

💡 **الآن اختر طرق الدفع الجديدة:**
(يمكنك اختيار أكثر من خيار)
"""
    
    payment_methods_map = {
        "الهرم": "payment_harm",
        "الهرم (دولار)": "payment_harm_usd",
        "الفؤاد": "payment_fouad",
        "الفؤاد (دولار)": "payment_fouad_usd",
        "شخاشيرو": "payment_shkhashiro",
        "شخاشيرو (دولار)": "payment_shkhashiro_usd",
        "ام تي ان كاش": "payment_mtn_cash",
        "سيريتل كاش": "payment_syriatel_cash",
        "شام كاش": "payment_sham_cash",
        "شام كاش (دولار)": "payment_sham_cash_usd",
        "القدموس": "payment_qadmous"
    }
    
    keyboard = []
    
    for method_name, callback_data in payment_methods_map.items():
        if method_name in editing_state['payment_methods']:
            button_text = f"✓ {method_name}"
        else:
            button_text = method_name
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"edit_{callback_data}")])
    
    keyboard.append([
        InlineKeyboardButton("✅ انتهى", callback_data="edit_payment_done"),
        InlineKeyboardButton("❌ إلغاء التعديل", callback_data="edit_cancel")
    ])
    
    selected_methods = "\n".join([f"• {method}" for method in editing_state['payment_methods']]) if editing_state['payment_methods'] else "لم يتم اختيار أي طريقة بعد"
    
    await update.message.reply_text(
        f"{payment_methods_text}\n💳 **طرق الدفع المختارة:**\n{selected_methods}\n\n👇 **اختر طرق الدفع المناسبة:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def confirm_offer_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in editing_offers:
        await query.answer("❌ انتهت جلسة التعديل", show_alert=True)
        return
    
    editing_state = editing_offers[user_id]
    
    payment_methods_text = "\n".join([f"• {method}" for method in editing_state['payment_methods']])
    
    confirm_text = f"""✅ **تفاصيل العرض بعد التعديل:**

📊 **معلومات العرض المعدل:**
📦 **النوع:** {editing_state['offer_type']}
💰 **السعر:** {editing_state['price']:,.2f} ليرة لكل USDT
🔢 **الحد الأدنى:** {editing_state['min_amount']} USDT
🔢 **الحد الأقصى:** {editing_state['max_amount']} USDT

💡 **تأكيد التعديل:** 
• سيتم تحديث العرض مباشرة 
• لن يحتاج العرض للمراجعة مرة أخرى 
• سيتم إعلام الإدارة بالتحديث 

💳 **طرق الدفع الجديدة:**
{payment_methods_text}

⚠️ **هل أنت متأكد من حفظ التعديلات؟**
"""
    
    await query.edit_message_text(
        confirm_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، احفظ التعديلات", callback_data=f"save_edit_{editing_state['offer_id']}")],
            [InlineKeyboardButton("❌ لا، ألغي التعديل", callback_data="edit_cancel")]
        ]),
        parse_mode='Markdown'
    )

async def save_offer_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in editing_offers:
        await query.answer("❌ انتهت جلسة التعديل", show_alert=True)
        return
    
    editing_state = editing_offers[user_id]
    
    if editing_state['offer_id'] != offer_id:
        await query.answer("❌ خطأ في رقم العرض", show_alert=True)
        return
    
    try:
        db = DatabaseManager()
        success = db.update_offer(
            offer_id=offer_id,
            min_amount=editing_state['min_amount'],
            max_amount=editing_state['max_amount'],
            price=editing_state['price'],
            payment_method=','.join(editing_state['payment_methods'])
        )
        
        if success:
            del editing_offers[user_id]
            
            await query.edit_message_text(
                f"""✅ **تم تحديث العرض #{offer_id} بنجاح!**

🎉 **تم حفظ جميع التعديلات بنجاح**

📋 **التعديلات التي تمت:**
• **السعر:** {editing_state['price']:,.2f} ليرة/USDT
• **الكمية:** {editing_state['min_amount']} - {editing_state['max_amount']} USDT
• **طرق الدفع:** {', '.join(editing_state['payment_methods'][:2])}{' و أكثر...' if len(editing_state['payment_methods']) > 2 else ''}

📢 **سيتم تحديث العرض في القناة الرسمية تلقائياً.**

🏠 **العودة لإدارة العروض:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 العودة لإدارة العروض", callback_data="my_offers")],
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
            
            await update_channel_offer_message(update, context, offer_id, completed=False)
            
        else:
            await query.edit_message_text(
                "❌ **حدث خطأ في حفظ التعديلات. يرجى المحاولة لاحقاً.**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 المحاولة مجدداً", callback_data=f"manage_offer_{offer_id}")]
                ]),
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logging.error(f"خطأ في حفظ تعديل العرض: {e}")
        await query.edit_message_text(
            "❌ **حدث خطأ في حفظ التعديلات. يرجى المحاولة لاحقاً.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 المحاولة مجدداً", callback_data=f"manage_offer_{offer_id}")]
            ]),
            parse_mode='Markdown'
        )

async def delete_offer_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    offer_id, offer_user_id, offer_type, min_amount, max_amount, price, _, _, _, _, _, created_at, _, _, _, _, _, _, _, _ = offer
    
    if offer_user_id != user_id:
        await query.answer("⚠️ ليس لديك صلاحية حذف هذا العرض", show_alert=True)
        return
    
    confirmation_text = f"""
⚠️ **تأكيد حذف العرض #{offer_id}**

📋 **تفاصيل العرض الذي تريد حذفه:**
• **النوع:** {offer_type}
• **السعر:** {price:,.2f} ليرة/USDT
• **الكمية:** {min_amount} - {max_amount} USDT
• **تاريخ الإنشاء:** {created_at[:16]}

🚨 **تحذير:** 
• هذا الإجراء لا يمكن التراجع عنه
• سيتم حذف العرض نهائياً
• سيتم إزالة العرض من القناة الرسمية

❓ **هل أنت متأكد من حذف هذا العرض؟**
"""
    
    await query.edit_message_text(
        confirmation_text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ نعم، احذف العرض", callback_data=f"confirm_delete_{offer_id}"),
                InlineKeyboardButton("❌ لا، أرجع", callback_data=f"manage_offer_{offer_id}")
            ]
        ]),
        parse_mode='Markdown'
    )

async def confirm_delete_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    offer_id, offer_user_id, _, _, _, _, _, _, _, _, _, _, channel_message_id, _, _, _, _, _, _, _ = offer
    
    if offer_user_id != user_id:
        await query.answer("⚠️ ليس لديك صلاحية حذف هذا العرض", show_alert=True)
        return
    
    try:
        success, deleted_channel_message_id = db.delete_offer(offer_id)
        
        if success:
            if deleted_channel_message_id and deleted_channel_message_id != 0:
                try:
                    await context.bot.delete_message(
                        chat_id=CHANNEL_ID,
                        message_id=deleted_channel_message_id
                    )
                except Exception as e:
                    logging.error(f"خطأ في حذف رسالة العرض من القناة: {e}")
            
            await query.edit_message_text(
                f"""✅ **تم حذف العرض #{offer_id} بنجاح!**

🗑️ **تم حذف العرض نهائياً من النظام.**

📢 **تم إزالة العرض من القناة الرسمية.**

🏠 **العودة لإدارة العروض:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 العودة لإدارة العروض", callback_data="my_offers")],
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ **حدث خطأ في حذف العرض. يرجى المحاولة لاحقاً.**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 العودة", callback_data=f"manage_offer_{offer_id}")]
                ]),
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logging.error(f"خطأ في حذف العرض: {e}")
        await query.edit_message_text(
            "❌ **حدث خطأ في حذف العرض. يرجى المحاولة لاحقاً.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة", callback_data=f"manage_offer_{offer_id}")]
            ]),
            parse_mode='Markdown'
        )

# ============ طلبات المستخدم (الميزة الجديدة) ============
async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    db = DatabaseManager()
    
    pending_requests = db.get_user_pending_requests(user_id)
    
    if not pending_requests:
        requests_text = """
🔄 **طلباتي**

📭 **لا توجد طلبات معلقة حالياً**

💡 **يمكنك:**
• تصفح العروض المتاحة
• إنشاء عروض جديدة
• انتظار موافقة على طلباتك السابقة
"""
        
        keyboard = [
            [InlineKeyboardButton("🛒 تصفح العروض", callback_data="browse_offers")],
            [InlineKeyboardButton("💎 إنشاء عرض", callback_data="create_offer")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
        ]
        
        await query.edit_message_text(
            requests_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    requests_text = f"""
🔄 **طلباتي**

📊 **عدد الطلبات المعلقة:** {len(pending_requests)}

👇 **اختر الطلب الذي تريد إدارته:**
"""
    
    keyboard = []
    
    for request in pending_requests[:10]:
        transaction_id = request[0]
        offer_id = request[1]
        buyer_id = request[2]
        seller_id = request[3]
        amount = request[4]
        price = request[5]
        payment_method = request[7]
        status = request[8]
        offer_type = request[19] if len(request) > 19 else "غير معروف"
        
        if user_id == buyer_id:
            request_type = "شراء" if offer_type == "بيع" else "بيع"
            other_party = seller_id
        else:
            request_type = "بيع" if offer_type == "بيع" else "شراء"
            other_party = buyer_id
        
        status_emoji = "⏳" if status == 'pending_approval' else "✅" if status == 'active' else "❌"
        
        request_button_text = f"{status_emoji} طلب #{transaction_id} ({request_type}) - {amount} USDT"
        keyboard.append([InlineKeyboardButton(request_button_text, callback_data=f"manage_request_{transaction_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
    ])
    
    await query.edit_message_text(
        requests_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def manage_specific_request(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    transaction = db.get_transaction_by_id(transaction_id)
    
    if not transaction:
        await query.answer("❌ الطلب غير موجود", show_alert=True)
        return
    
    transaction_details = transaction
    
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, buyer_name, seller_username, seller_name, offer_type, offer_payment_methods = transaction_details
    
    if user_id not in [buyer_id, seller_id]:
        await query.answer("⚠️ ليس لديك صلاحية إدارة هذا الطلب", show_alert=True)
        return
    
    is_buyer = user_id == buyer_id
    other_party_name = seller_name if is_buyer else buyer_name
    other_party_username = seller_username if is_buyer else buyer_username
    
    request_type = "شراء" if (is_buyer and offer_type == "بيع") or (not is_buyer and offer_type == "شراء") else "بيع"
    
    request_details = f"""
📋 **تفاصيل الطلب #{transaction_id}**

📊 **معلومات الطلب:**
├ 📝 **النوع:** {request_type} USDT
├ 💰 **الكمية:** {amount} USDT
├ 📈 **السعر:** {price:,.2f} ليرة/USDT
├ 💵 **المجموع:** {total_price:,.2f} ليرة
├ 💳 **طريقة الدفع:** {payment_method}
├ ⏳ **الحالة:** {status}
├ 👤 **الطرف الآخر:** {other_party_name or other_party_username or f"المستخدم {seller_id if is_buyer else buyer_id}"}
└ 📅 **تاريخ الطلب:** {created_at[:16]}

💡 **خيارات الإدارة:**
"""
    
    keyboard = []
    
    if is_buyer and status == 'pending_approval':
        keyboard.append([InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f"cancel_request_{transaction_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("🔙 رجوع للطلبات", callback_data="my_requests")],
        [
            InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main"),
            InlineKeyboardButton("📞 التواصل مع الدعم", url=f"tg://resolve?domain={SUPPORT_USERNAME[1:]}")
        ]
    ])
    
    await query.edit_message_text(
        request_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def cancel_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    success = db.cancel_user_transaction(user_id, transaction_id)
    
    if success:
        await query.edit_message_text(
            f"""✅ **تم إلغاء الطلب #{transaction_id} بنجاح!**

🗑️ **تم إلغاء طلبك بنجاح.**

📋 **سيتم إعلام الطرف الآخر بالإلغاء.**

🏠 **العودة للطلبات:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 العودة للطلبات", callback_data="my_requests")],
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
    else:
        await query.answer("❌ لا يمكن إلغاء هذا الطلب", show_alert=True)

# ============ الموافقة على طلبات البيع/الشراء ============
async def handle_seller_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id, approve=True):
    query = update.callback_query
    user_id = query.from_user.id
    
    db = DatabaseManager()
    transaction = db.get_transaction_by_id(transaction_id)
    
    if not transaction:
        await query.answer("❌ المعاملة غير موجودة", show_alert=True)
        return
    
    transaction_details = transaction
    
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, buyer_name, seller_username, seller_name, offer_type, offer_payment_methods = transaction_details
    
    if user_id != seller_id:
        await query.answer("⚠️ ليس لديك صلاحية الموافقة على هذا الطلب", show_alert=True)
        return
    
    if status != 'pending_approval':
        await query.answer("⚠️ هذا الطلب ليس بانتظار الموافقة", show_alert=True)
        return
    
    if approve:
        db.set_seller_approved(transaction_id)
        await update_channel_offer_message(update, context, offer_id, completed=True)
        
        await query.edit_message_text(
            f"""✅ **تمت الموافقة على الطلب #{transaction_id}**

🎉 **وافقت على طلب {offer_type} عرضك رقم {offer_id}**

📋 **تفاصيل الطلب المقبول:**
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {payment_method}

👤 **المشتري:** {buyer_name or buyer_username or f"المستخدم {buyer_id}"}

💡 **الخطوات التالية:**
1. سيتم إعلام المشتري بالموافقة
2. سيقوم المشتري بإرسال USDT لمحفظة البوت
3. بعد تأكيد الإستلام، سيتم إعلامك لإرسال المبلغ للزبون
4. بعد تأكيد وصول المبلغ، سيتم إرسال USDT للمشتري

🏠 **من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=f"""✅ **تمت الموافقة على طلبك!**

🎉 **البائع وافق على طلب {offer_type} رقم {transaction_id}**

📋 **تفاصيل الطلب المقبول:**
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {payment_method}

💡 **الخطوات التالية:**
1. أرسل {amount} USDT إلى محفظة البوت
2. أدخل معرف المعاملة (Transaction Hash)
3. سيتم التحقق من التحويل
4. بعد التحقق، سيتم إعلام البائع لإرسال المبلغ لك

🏦 **محفظة البوت:** `{BOT_WALLET_ADDRESS}`

⚠️ **مهم:** أرسل المبلغ المحدد فقط ({amount} USDT)

✏️ **أدخل معرف المعاملة (Transaction Hash) الآن:**""",
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال إشعار للمشتري: {e}")
        
    else:
        db.set_seller_rejected(transaction_id)
        
        await query.edit_message_text(
            f"""❌ **تم رفض الطلب #{transaction_id}**

🚫 **رفضت طلب {offer_type} عرضك رقم {offer_id}**

📋 **تفاصيل الطلب المرفوض:**
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {payment_method}

👤 **المشتري:** {buyer_name or buyer_username or f"المستخدم {buyer_id}"}

💡 **تم إعلام المشتري بالرفض.**

🏠 **من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=f"""❌ **تم رفض طلبك**

🚫 **البائع رفض طلب {offer_type} رقم {transaction_id}**

📋 **تفاصيل الطلب المرفوض:**
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {payment_method}

💡 **يمكنك:**
• تصفح عروض أخرى
• تقديم طلب جديد

🏠 **من الواجهة الرئيسية:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 تصفح عروض أخرى", callback_data="browse_offers")],
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال إشعار للمشتري: {e}")

# ============ معالجة إدخال معرف المعاملة ============
async def handle_usdt_transaction_hash(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, transaction_hash: str):
    """معالجة إدخال معرف معاملة USDT"""
    try:
        db = DatabaseManager()
        
        user_transactions_list = db.get_user_transactions(user_id, status='active')
        if not user_transactions_list:
            await update.message.reply_text(
                "❌ **لا توجد معاملات نشطة تحتاج لإدخال معرف معاملة**",
                parse_mode='Markdown'
            )
            return
        
        latest_transaction = user_transactions_list[0]
        transaction_id = latest_transaction[0]
        
        db.update_transaction_usdt_hash(transaction_id, transaction_hash)
        
        await update.message.reply_text(
            f"""✅ **تم حفظ معرف المعاملة بنجاح!**

🔗 **Transaction Hash:** `{transaction_hash[:20]}...`

📋 **رقم المعاملة:** #{transaction_id}

💡 **سيتم التحقق من التحويل من قبل الإدارة.**
⏳ **قد تستغرق عملية التحقق بعض الوقت.**

📞 **للاستفسار، تواصل مع الدعم.**

🏠 **من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
        
        db.add_notification(
            notification_type='usdt_received',
            user_id=user_id,
            transaction_id=transaction_id,
            message=f'تم إدخال معرف معاملة USDT للمعاملة #{transaction_id}: {transaction_hash[:20]}...'
        )
        
    except Exception as e:
        logging.error(f"خطأ في حفظ معرف المعاملة: {e}")
        await update.message.reply_text(
            "❌ **حدث خطأ في حفظ معرف المعاملة. يرجى المحاولة لاحقاً.**",
            parse_mode='Markdown'
        )

# ============ استمرار القسم التالي...
# استمرار القسم 2 من 3

# ============ تصفح العروض ============
async def browse_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    browse_text = """
🛒 **تصفح العروض المتاحة**

✨ **اختر نوع العروض التي تريد تصفحها:**

💎 **عروض البيع (لشراء USDT)**
تصفح العروض المتاحة للشراء

💰 **عروض الشراء (لبيع USDT)**
تصفح العروض المتاحة للبيع

👇 **اختر الخيار المناسب لك:**
    """
    
    keyboard = [
        [InlineKeyboardButton("💎 عروض البيع", callback_data="view_buy_offers")],
        [InlineKeyboardButton("💰 عروض الشراء", callback_data="view_sell_offers")],
        [InlineKeyboardButton("🏠 العودة للواجهة الرئيسية", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        browse_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def browse_offers_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browse_text = """
🛒 **تصفح العروض المتاحة**

✨ **اختر نوع العروض التي تريد تصفحها:**

💎 **عروض البيع (لشراء USDT)**
تصفح العروض المتاحة للشراء

💰 **عروض الشراء (لبيع USDT)**
تصفح العروض المتاحة للبيع

👇 **اختر الخيار المناسب لك:**
    """
    
    keyboard = [
        [InlineKeyboardButton("💎 عروض البيع", callback_data="view_buy_offers")],
        [InlineKeyboardButton("💰 عروض الشراء", callback_data="view_sell_offers")],
        [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        browse_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def view_buy_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    if user_id in offer_filters:
        del offer_filters[user_id]
    
    filter_state = OfferFilterState()
    filter_state.offer_type = "بيع"
    offer_filters[user_id] = filter_state
    
    await show_buy_offer_categories(update, context)

async def show_buy_offer_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    offers_text = """
🔎 **تصفح عروض البيع (للشراء)**

📋 **اختر فئة العروض:**

📱 **Syriatel/MTN Cash**
عرض العروض التي اختار صاحب العرض فيها طريقة الدفع سيريتل كاش أو ام تي ان كاش

💸 **حوالات مالية داخلية**
عرض العروض التي اختار صاحب العرض فيها طريقة الدفع:
الهرم، الهرم (دولار)، شخاشيرو، شخاشيرو (دولار)، الفؤاد، الفؤاد (دولار)، القدموس

🏦 **Sham Cash $ & s.p**
عرض العروض التي اختار صاحب العرض فيها طريقة الدفع:
شام كاش، شام كاش (دولار)
    """
    
    keyboard = [
        [InlineKeyboardButton("📱 Syriatel/MTN Cash", callback_data="filter_category_mobile_cash_buy")],
        [InlineKeyboardButton("💸 حوالات مالية داخلية", callback_data="filter_category_internal_transfers_buy")],
        [InlineKeyboardButton("🏦 Sham Cash $ & s.p", callback_data="filter_category_sham_cash_buy")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="browse_offers")]
    ]
    
    await query.edit_message_text(
        offers_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def view_sell_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    if user_id in offer_filters:
        del offer_filters[user_id]
    
    filter_state = OfferFilterState()
    filter_state.offer_type = "شراء"
    offer_filters[user_id] = filter_state
    
    await show_sell_offer_categories(update, context)

async def show_sell_offer_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    offers_text = """
🔎 **تصفح عروض الشراء (للبيع)**

📋 **اختر فئة العروض:**

📱 **Syriatel/MTN Cash**
عرض العروض التي اختار صاحب العرض فيها طريقة الدفع سيريتل كاش أو ام تي ان كاش

💸 **حوالات مالية داخلية**
عرض العروض التي اختار صاحب العرض فيها طريقة الدفع:
الهرم، الهرم (دولار)، شخاشيرو، شخاشيرو (دولار)، الفؤاد، الفؤاد (دولار)، القدموس

🏦 **Sham Cash $ & s.p**
عرض العروض التي اختار صاحب العرض فيها طريقة الدفع:
شام كاش، شام كاش (دولار)
    """
    
    keyboard = [
        [InlineKeyboardButton("📱 Syriatel/MTN Cash", callback_data="filter_category_mobile_cash_sell")],
        [InlineKeyboardButton("💸 حوالات مالية داخلية", callback_data="filter_category_internal_transfers_sell")],
        [InlineKeyboardButton("🏦 Sham Cash $ & s.p", callback_data="filter_category_sham_cash_sell")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="browse_offers")]
    ]
    
    await query.edit_message_text(
        offers_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in offer_filters:
        await query.answer("❌ انتهت جلسة التصفية", show_alert=True)
        return
    
    filter_state = offer_filters[user_id]
    
    if data.endswith("_buy"):
        filter_state.offer_type = "بيع"
        category_key = data.replace("filter_category_", "").replace("_buy", "")
    elif data.endswith("_sell"):
        filter_state.offer_type = "شراء"
        category_key = data.replace("filter_category_", "").replace("_sell", "")
    else:
        await query.answer("❌ خطأ في اختيار الفئة", show_alert=True)
        return
    
    filter_state.category = category_key
    filter_state.page = 0
    filter_state.sort_order = "newest"
    
    await show_filtered_offers(update, context, user_id)

async def show_filtered_offers(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    
    if user_id not in offer_filters:
        if query:
            await query.answer("❌ انتهت جلسة التصفية", show_alert=True)
        return
    
    filter_state = offer_filters[user_id]
    
    db = DatabaseManager()
    offers, total_count = db.get_filtered_offers(
        filter_state.offer_type,
        filter_state.category,
        filter_state.sort_order,
        filter_state.page
    )
    
    category_name = PAYMENT_CATEGORIES[filter_state.category]["name"] if filter_state.category else "الكل"
    offer_type_arabic = "بيع" if filter_state.offer_type == "بيع" else "شراء"
    order_text = {
        "newest": "🆕 الأحدث",
        "price_asc": "📈 تصاعدي حسب السعر",
        "price_desc": "📉 تنازلي حسب السعر"
    }.get(filter_state.sort_order, "🆕 الأحدث")
    
    start_idx = filter_state.page * OFFERS_PER_PAGE + 1
    end_idx = min((filter_state.page + 1) * OFFERS_PER_PAGE, total_count)
    
    offers_text = f"""
🔍 **تصفح عروض {offer_type_arabic}**

📋 **الفئة:** {category_name}
🔢 **العروض:** {start_idx}-{end_idx} من {total_count}
📊 **الترتيب:** {order_text}

━━━━━━━━━━━━━━━━━━━━
    """
    
    if not offers:
        offers_text += "\n📭 **لا توجد عروض متاحة حالياً في هذه الفئة**\n\n"
        offers_text += "✨ **كن أول من ينشر عرض في هذه الفئة!**"
    else:
        for idx, offer in enumerate(offers, start_idx):
            offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, reputation, completion_rate, total_transactions, user_level = offer
            
            username_display = f"@{username}" if username else "مستخدم"
            payment_methods = payment_method.split(',')
            payment_display = payment_methods[0] + (" +..." if len(payment_methods) > 1 else "")
            completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
            offer_emoji = "🔴" if offer_type == "بيع" else "🟢"
            
            offers_text += f"""
{offer_emoji} **العرض #{offer_id}**
┌ 💰 **السعر:** {price:,.2f} ليرة/USDT
├ 📦 **الكمية:** {min_amount}-{max_amount} USDT
├ 👤 **التاجر:** {username_display} 🏆{user_level}
├ 💳 **الدفع:** {payment_display}
├ 📊 **الإتمام:** {completion_rate_display}%
└ 📅 **النشر:** {created_at[:16]}

🔗 **للطلب اضغط هنا:**"""

            offers_text += f"\n[📨 طلب هذا العرض](https://t.me/Qcss_bot?start=offer_{offer_id})\n"
            
            if idx < end_idx:
                offers_text += "\n━━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = []
    sort_buttons = []
    
    if filter_state.sort_order != "newest":
        sort_buttons.append(InlineKeyboardButton("🆕 الأحدث", callback_data=f"sort_newest_{user_id}"))
    if filter_state.sort_order != "price_asc":
        sort_buttons.append(InlineKeyboardButton("📈 تصاعدي", callback_data=f"sort_price_asc_{user_id}"))
    if filter_state.sort_order != "price_desc":
        sort_buttons.append(InlineKeyboardButton("📉 تنازلي", callback_data=f"sort_price_desc_{user_id}"))
    
    if sort_buttons:
        keyboard.append(sort_buttons)
    
    nav_buttons = []
    if filter_state.page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"page_prev_{user_id}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {filter_state.page + 1}", callback_data="noop"))
    
    if (filter_state.page + 1) * OFFERS_PER_PAGE < total_count:
        nav_buttons.append(InlineKeyboardButton("▶️ التالي", callback_data=f"page_next_{user_id}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    back_button = []
    if filter_state.offer_type == "بيع":
        back_button.append(InlineKeyboardButton("🔙 رجوع للفئات", callback_data="view_buy_offers"))
    else:
        back_button.append(InlineKeyboardButton("🔙 رجوع للفئات", callback_data="view_sell_offers"))
    
    back_button.append(InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main"))
    keyboard.append(back_button)
    
    if query:
        await query.edit_message_text(
            offers_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            offers_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

async def show_offer_details(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await update.message.reply_text(
            "❌ **العرض غير موجود أو تم إزالته**\n\n"
            "🔙 **العودة للواجهة الرئيسية:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, first_name, reputation, completion_rate, total_transactions, completed_transactions, user_level = offer
    
    if status != 'active':
        await update.message.reply_text(
            "❌ **هذا العرض غير متاح حالياً**\n\n"
            "🔍 **قد يكون:**\n"
            "• قيد المراجعة\n"
            "• منتهي الصلاحية\n"
            "• مرفوض\n\n"
            "🔙 **العودة للواجهة الرئيسية:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    username_display = f"@{username}" if username else first_name or f"المستخدم {user_id}"
    offer_type_arabic = "بيع" if offer_type == "بيع" else "شراء"
    payment_methods = payment_method.split(',')
    
    avg_amount = (min_amount + max_amount) / 2
    commission = avg_amount * COMMISSION_RATE
    completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
    offer_emoji = "🔴" if offer_type == "بيع" else "🟢"
    
    offer_details = f"""
{offer_emoji} **تفاصيل العرض #{offer_id}**

📋 **معلومات العرض:**
┌ 📊 **النوع:** {offer_emoji} {offer_type_arabic} USDT
├ 💰 **السعر:** {price:,.2f} ليرة/USDT
├ 📦 **الكمية:** {min_amount} - {max_amount} USDT
├ ⏳ **المدة:** {transaction_duration} دقيقة
└ 📅 **النشر:** {created_at[:16]}

👤 **معلومات التاجر:**
┌ 🏷️ **الاسم:** {username_display}
├ 🏆 **المستوى:** {user_level}
├ 📊 **نسبة الإتمام:** {completion_rate_display}%
├ ⭐ **السمعة:** {reputation:.1f}
└ 📈 **الصفقات:** {total_transactions} ({completed_transactions} مكتملة)

💳 **طرق الدفع المتاحة:**
"""
    
    for i, method in enumerate(payment_methods, 1):
        offer_details += f"**{i}. {method}**\n"
    
    offer_details += f"""
📉 **عمولة الوسيط:** {commission:.2f}$ / {avg_amount:.0f}$

💡 **للإتمام الصفقة، اتبع الخطوات التالية:**
1. تأكد من توفر المبلغ المطلوب
2. قم بالتواصل مع البائع
3. استخدم وسيط موثوق للمعاملة
4. احتفظ بسجلات الدفع
"""
    
    keyboard = []
    
    if offer_type == "بيع":
        keyboard.append([InlineKeyboardButton("🛒 شراء هذا العرض", callback_data=f"start_purchase_{offer_id}")])
    else:
        keyboard.append([InlineKeyboardButton("💰 البيع لهذا العرض", callback_data=f"start_purchase_{offer_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("🔍 تصفح عروض أخرى", callback_data="browse_offers")],
        [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
    ])
    
    await update.message.reply_text(
        offer_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def start_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    offer_id, seller_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, first_name, reputation, completion_rate, total_transactions, completed_transactions, user_level = offer
    
    if status != 'active':
        await query.answer("❌ هذا العرض غير متاح حالياً", show_alert=True)
        return
    
    user_id = query.from_user.id
    payment_methods = payment_method.split(',')
    
    transaction_state = TransactionState(
        user_id=user_id,
        offer_id=offer_id,
        offer_type=offer_type,
        seller_id=seller_id,
        price=price,
        min_amount=min_amount,
        max_amount=max_amount,
        payment_methods=payment_methods
    )
    
    user_transactions[user_id] = transaction_state
    context.user_data['awaiting_transaction_amount'] = True
    
    action_text = "شراء" if offer_type == "بيع" else "بيع"
    
    await query.edit_message_text(
        f"""📝 **بدء عملية {action_text}**

📋 **معلومات العرض المحدد:**
• **رقم العرض:** #{offer_id}
• **النوع:** {'بيع' if offer_type == 'بيع' else 'شراء'}
• **السعر:** {price:,.2f} ليرة/USDT
• **نطاق الكمية:** {min_amount} - {max_amount} USDT

💡 **الرجاء إدخال الكمية التي تريد {action_text}ها:**
(يجب أن تكون الكمية بين {min_amount} و {max_amount} USDT)

✏️ **أدخل الكمية الآن:**""",
        parse_mode='Markdown'
    )

async def handle_sort_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = int(data.split("_")[-1])
    
    if user_id not in offer_filters:
        await query.answer("❌ انتهت جلسة التصفية", show_alert=True)
        return
    
    filter_state = offer_filters[user_id]
    
    if "sort_newest" in data:
        filter_state.sort_order = "newest"
    elif "sort_price_asc" in data:
        filter_state.sort_order = "price_asc"
    elif "sort_price_desc" in data:
        filter_state.sort_order = "price_desc"
    
    filter_state.page = 0
    await show_filtered_offers(update, context, user_id)

async def handle_page_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = int(data.split("_")[-1])
    
    if user_id not in offer_filters:
        await query.answer("❌ انتهت جلسة التصفية", show_alert=True)
        return
    
    filter_state = offer_filters[user_id]
    
    if "page_prev" in data:
        if filter_state.page > 0:
            filter_state.page -= 1
    elif "page_next" in data:
        filter_state.page += 1
    
    await show_filtered_offers(update, context, user_id)

# ============ معالجة اختيار طريقة الدفع في المعاملة ============
async def handle_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in user_transactions:
        await query.answer("❌ انتهت جلسة المعاملة", show_alert=True)
        return
    
    transaction_state = user_transactions[user_id]
    
    if data.startswith("select_payment_"):
        selected_method = data.replace("select_payment_", "")
        
        if selected_method not in transaction_state.selected_payment_methods:
            await query.answer("❌ طريقة الدفع غير متاحة", show_alert=True)
            return
        
        transaction_state.selected_payment_method = selected_method
        total_price = transaction_state.selected_amount * transaction_state.price
        action_text = "شراء" if transaction_state.offer_type == "بيع" else "بيع"
        
        confirmation_text = f"""
✅ **تفاصيل طلبك النهائية**

📋 **معلومات الطلب:**
┌ 📊 **النوع:** {action_text} USDT
├ 🔢 **رقم العرض:** #{transaction_state.offer_id}
├ 💰 **الكمية:** {transaction_state.selected_amount} USDT
├ 📈 **السعر:** {transaction_state.price:,.2f} ليرة/USDT
├ 💵 **المجموع:** {total_price:,.2f} ليرة
└ 💳 **طريقة الدفع:** {selected_method}

👤 **معلومات الطرف الآخر:**
• **معرف التاجر:** {transaction_state.seller_id}
• **نوع العرض:** {'بيع' if transaction_state.offer_type == 'بيع' else 'شراء'}

⚠️ **تأكيد الطلب:**
بعد التأكيد، سيتم إرسال طلبك إلى إدارة النظام للمراجعة والموافقة.

🔒 **ملاحظة:** جميع المعاملات تتم تحت إشراف الإدارة لضمان الأمان.
"""
        
        keyboard = [
            [
                InlineKeyboardButton("✅ تأكيد الطلب", callback_data="confirm_transaction"),
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel_transaction")
            ]
        ]
        
        await query.edit_message_text(
            confirmation_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif data == "cancel_transaction":
        if user_id in user_transactions:
            del user_transactions[user_id]
        
        for key in ['awaiting_transaction_amount', 'awaiting_payment_method']:
            if key in context.user_data:
                del context.user_data[key]
        
        await query.edit_message_text(
            "❌ **تم إلغاء العملية**\n\n"
            "🏠 **العودة للواجهة الرئيسية:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )

async def confirm_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in user_transactions:
        await query.answer("❌ انتهت جلسة المعاملة", show_alert=True)
        return
    
    transaction_state = user_transactions[user_id]
    
    if not transaction_state.selected_amount or not transaction_state.selected_payment_method:
        await query.answer("❌ البيانات غير مكتملة", show_alert=True)
        return
    
    total_price = transaction_state.selected_amount * transaction_state.price
    
    try:
        db = DatabaseManager()
        transaction_id = db.add_transaction(
            offer_id=transaction_state.offer_id,
            buyer_id=user_id,
            seller_id=transaction_state.seller_id,
            amount=transaction_state.selected_amount,
            price=transaction_state.price,
            total_price=total_price,
            payment_method=transaction_state.selected_payment_method
        )
        
        action_text = "شراء" if transaction_state.offer_type == "بيع" else "بيع"
        
        await query.edit_message_text(
            f"""✅ **تم إرسال طلبك بنجاح!**

🎉 **طلب {action_text} #{transaction_id} تم إرساله للمراجعة**

📋 **تفاصيل الطلب المرسل:**
• **رقم الطلب:** #{transaction_id}
• **الكمية:** {transaction_state.selected_amount} USDT
• **السعر:** {transaction_state.price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {transaction_state.selected_payment_method}

⏰ **مدة المراجعة:** سيتم مراجعة طلبك من قبل الإدارة قريباً
🔔 **سيتم إشعارك عند قبول أو رفض الطلب**

🏠 **العودة للواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")],
                [InlineKeyboardButton("🛒 تصفح المزيد", callback_data="browse_offers")]
            ]),
            parse_mode='Markdown'
        )
        
        del user_transactions[user_id]
        
        for key in ['awaiting_transaction_amount', 'awaiting_payment_method']:
            if key in context.user_data:
                del context.user_data[key]
        
        # إرسال إشعار للبائع
        await notify_seller_new_request(
            update, context, 
            transaction_id, 
            user_id, 
            transaction_state.offer_id, 
            transaction_state.selected_amount, 
            transaction_state.selected_payment_method
        )
        
    except Exception as e:
        logging.error(f"خطأ في حفظ المعاملة: {e}")
        await query.edit_message_text(
            "❌ **حدث خطأ في إرسال طلبك. يرجى المحاولة لاحقاً.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 المحاولة مجدداً", callback_data=f"start_purchase_{transaction_state.offer_id}")
                if transaction_state.offer_id else InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )

# ============ إنشاء عرض جديد ============
async def create_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    create_text = """
💡 **اختر نوع العملية التي تريد القيام بها:**

🔥 **خيارات متاحة لك:**

💰 **بيع العملات الرقمية**
• حدد السعر الذي يناسبك للبيع
• حدد أقل وأعلى كمية تريد بيعها
• حدد طريقة استلامك بالليرة السورية

💎 **شراء العملات الرقمية**
• حدد السعر الذي يناسبك للشراء
• حدد أقل وأعلى كمية تريد شراءها
• حدد طريقة دفعك بالليرة السورية

🌟 **اختر ماذا تريد وابدأ الآن:**
    """
    
    keyboard = [
        [InlineKeyboardButton("💰 بيع العملات الرقمية", callback_data="sell_crypto_offer")],
        [InlineKeyboardButton("💎 شراء العملات الرقمية", callback_data="buy_crypto_offer")],
        [InlineKeyboardButton("🏠 العودة للواجهة الرئيسية", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        create_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def sell_crypto_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    user_states[user_id] = OfferState(user_id)
    
    tips_text = """
💡 **نصائح للبدء:** 
• تأكد من توفر العملة الرقمية لديك 
• حدد سعر منافس في السوق 
• اختر طرق دفع متنوعة لتنفيذ بشكل أسرع 

🚀 **ابدأ الآن بعملية 🔴 بيع 🔴 ممتعة** 

💰 **ادخل السعر الذي تراه مناسب لكَ:**
(السعر بالليرة السورية لكل 1 USDT)
"""
    
    await query.edit_message_text(
        tips_text,
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_price'] = True
    context.user_data['creating_sell_offer'] = True

async def buy_crypto_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    user_states[user_id] = OfferState(user_id)
    user_states[user_id].offer_type = "شراء"
    
    tips_text = """
💡 **نصائح للبدء:** 
• تأكد من توفر العملة الرقمية لديك 
• حدد سعر منافس في السوق 
• اختر طرق دفع متنوعة لتنفيذ بشكل أسرع 

🚀 **ابدأ الآن بعملية 🔵 شراء 🔵 ممتعة** 

💰 **ادخل السعر الذي تراه مناسب لكَ:**
(السعر بالليرة السورية لكل 1 USDT)
"""
    
    await query.edit_message_text(
        tips_text,
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_price'] = True
    context.user_data['creating_buy_offer'] = True

async def show_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states[user_id]
    
    offer_type_arabic = "بيع" if state.offer_type == "بيع" else "شراء"
    offer_type_emoji = "🔴 بيع 🔴" if state.offer_type == "بيع" else "🔵 شراء 🔵"
    
    payment_methods_text = f"""📋 **تفاصيل العرض:**

📊 **نوع العرض :** {offer_type_emoji}
💰 **السعر :** {state.price:,.2f} ليرة/USDT
🔢 **الحد الأدنى :** {state.min_amount} USDT
🔢 **الحد الأقصى :** {state.max_amount} USDT

💡 **نصائح:** 
• اختر طرق دفع متنوعة لتنفيذ أسرع 
• طرق دفع أكثر تعني فرص أفضل 
• تأكد من توفر حساباتك لهذه الطرق 

💳 **ما هي طرق الدفع التي تقبل{' الدفع بها' if state.offer_type == 'بيع' else ' الاستلام بها'} لك؟**

👇 **اختر طرق الدفع المناسبة:**
(يمكنك اختيار أكثر من خيار)
"""
    
    keyboard = [
        [InlineKeyboardButton("✅ الهرم", callback_data="payment_harm")],
        [InlineKeyboardButton("✅ الهرم (دولار)", callback_data="payment_harm_usd")],
        [InlineKeyboardButton("✅ الفؤاد", callback_data="payment_fouad")],
        [InlineKeyboardButton("✅ الفؤاد (دولار)", callback_data="payment_fouad_usd")],
        [InlineKeyboardButton("✅ شخاشيرو", callback_data="payment_shkhashiro")],
        [InlineKeyboardButton("✅ شخاشيرو (دولار)", callback_data="payment_shkhashiro_usd")],
        [InlineKeyboardButton("✅ ام تي ان كاش", callback_data="payment_mtn_cash")],
        [InlineKeyboardButton("✅ سيريتل كاش", callback_data="payment_syriatel_cash")],
        [InlineKeyboardButton("✅ شام كاش", callback_data="payment_sham_cash")],
        [InlineKeyboardButton("✅ شام كاش (دولار)", callback_data="payment_sham_cash_usd")],
        [InlineKeyboardButton("✅ القدموس", callback_data="payment_qadmous")],
        [
            InlineKeyboardButton("✅ انتهى", callback_data="payment_done"),
            InlineKeyboardButton("❌ إلغاء", callback_data="payment_cancel")
        ]
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            payment_methods_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.callback_query.edit_message_text(
            payment_methods_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def handle_payment_selection_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in user_states:
        await query.edit_message_text("❌ انتهت الجلسة. يرجى البدء من جديد.")
        return
    
    state = user_states[user_id]
    
    payment_methods_map = {
        "payment_harm": "الهرم",
        "payment_harm_usd": "الهرم (دولار)",
        "payment_fouad": "الفؤاد",
        "payment_fouad_usd": "الفؤاد (دولار)",
        "payment_shkhashiro": "شخاشيرو",
        "payment_shkhashiro_usd": "شخاشيرو (دولار)",
        "payment_mtn_cash": "ام تي ان كاش",
        "payment_syriatel_cash": "سيريتل كاش",
        "payment_sham_cash": "شام كاش",
        "payment_sham_cash_usd": "شام كاش (دولار)",
        "payment_qadmous": "القدموس"
    }
    
    if data in payment_methods_map:
        method = payment_methods_map[data]
        
        if method in state.payment_methods:
            state.payment_methods.remove(method)
        else:
            state.payment_methods.append(method)
        
        await update_payment_keyboard(query, state)
    
    elif data == "payment_done":
        if not state.payment_methods:
            await query.answer("⚠️ يرجى اختيار طريقة دفع واحدة على الأقل", show_alert=True)
            return
        
        await confirm_offer(update, context)
    
    elif data == "payment_cancel":
        await query.edit_message_text(
            "⚠️ **هل أنت متأكد من إلغاء إنشاء العرض؟**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ نعم، ألغي", callback_data="confirm_cancel")],
                [InlineKeyboardButton("❌ لا، أرجع", callback_data="cancel_cancel")]
            ]),
            parse_mode='Markdown'
        )

async def update_payment_keyboard(query, state):
    payment_methods = [
        ("الهرم", "payment_harm"),
        ("الهرم (دولار)", "payment_harm_usd"),
        ("الفؤاد", "payment_fouad"),
        ("الفؤاد (دولار)", "payment_fouad_usd"),
        ("شخاشيرو", "payment_shkhashiro"),
        ("شخاشيرو (دولار)", "payment_shkhashiro_usd"),
        ("ام تي ان كاش", "payment_mtn_cash"),
        ("سيريتل كاش", "payment_syriatel_cash"),
        ("شام كاش", "payment_sham_cash"),
        ("شام كاش (دولار)", "payment_sham_cash_usd"),
        ("القدموس", "payment_qadmous")
    ]
    
    keyboard = []
    for method_name, callback_data in payment_methods:
        if method_name in state.payment_methods:
            button_text = f"✓ {method_name}"
        else:
            button_text = method_name
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([
        InlineKeyboardButton("✅ انتهى", callback_data="payment_done"),
        InlineKeyboardButton("❌ إلغاء", callback_data="payment_cancel")
    ])
    
    selected_methods = "\n".join([f"• {method}" for method in state.payment_methods]) if state.payment_methods else "لم يتم اختيار أي طريقة بعد"
    offer_type_emoji = "🔴 بيع 🔴" if state.offer_type == "بيع" else "🔵 شراء 🔵"
    
    await query.edit_message_text(
        f"""📋 **تفاصيل العرض:**

📊 **نوع العرض :** {offer_type_emoji}
💰 **السعر :** {state.price:,.2f} ليرة/USDT
🔢 **الحد الأدنى :** {state.min_amount} USDT
🔢 **الحد الأقصى :** {state.max_amount} USDT

💡 **نصائح:** 
• اختر طرق دفع متنوعة لتنفيذ أسرع 
• طرق دفع أكثر تعني فرص أفضل 
• تأكد من توفر حساباتك لهذه الطرق 

💳 **طرق الدفع المختارة:**
{selected_methods}

👇 **اختر طرق الدفع المناسبة:**""",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def confirm_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    state = user_states[user_id]
    
    payment_methods_text = "\n".join([f"• {method}" for method in state.payment_methods])
    offer_type_arabic = "بيع" if state.offer_type == "بيع" else "شراء"
    offer_type_emoji = "🔴 بيع 🔴" if state.offer_type == "بيع" else "🔵 شراء 🔵"
    
    confirm_text = f"""✅ **تفاصيل العرض النهائي:**

📊 **معلومات العرض:**
📦 **النوع:** {offer_type_emoji}
💰 **السعر:** {state.price:,.2f} ليرة لكل USDT
🔢 **الحد الأدنى:** {state.min_amount} USDT
🔢 **الحد الأقصى:** {state.max_amount} USDT

💡 **نصائح أخيرة:** 
• تأكد من صحة المعلومات المدخلة 
• يمكنك تعديل أي معلومة قبل الإرسال 
• بعد الإرسال، سيتم مراجعة العرض من قبل الإدارة 

💳 **طرق الدفع المقبولة:**
{payment_methods_text}

⚠️ **سيتم إرسال هذا العرض للمراجعة من قبل الإدارة قبل نشره**

🔍 **ملاحظة:** قد تستغرق عملية المراجعة حتى 24 ساعة.

⚠️ **هل أنت متأكد من إرسال هذا العرض للمراجعة؟**
"""
    
    await query.edit_message_text(
        confirm_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، أرسل للمراجعة", callback_data="publish_offer")],
            [InlineKeyboardButton("❌ لا، ألغي", callback_data="confirm_cancel")]
        ]),
        parse_mode='Markdown'
    )

async def publish_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in user_states:
        await query.edit_message_text("❌ انتهت الجلسة. يرجى البدء من جديد.")
        return
    
    state = user_states[user_id]
    
    try:
        db = DatabaseManager()
        offer_id = db.add_offer(
            user_id,
            state.offer_type,
            state.min_amount,
            state.max_amount,
            state.price,
            ','.join(state.payment_methods)
        )
        
        offer_type_arabic = "بيع" if state.offer_type == "بيع" else "شراء"
        
        await query.edit_message_text(
            f"""⏳ **تم إرسال عرضك للمراجعة!**

✅ **عرض #{offer_id} ({offer_type_arabic}) أُرسل للمراجعة**

📋 **تفاصيل العرض المرسل:**
• **النوع:** {offer_type_arabic}
• **السعر:** {state.price:,.2f} ليرة/USDT
• **الكمية:** {state.min_amount} - {state.max_amount} USDT
• **طرق الدفع:** {', '.join(state.payment_methods[:2])}{' و أكثر...' if len(state.payment_methods) > 2 else ''}

⏰ **مدة المراجعة:** قد تصل إلى 24 ساعة
🔔 **سيتم إشعارك عند قبول أو رفض العرض**
📢 **بعد الموافقة، سيتم نشر عرضك في قناة العروض: {CHANNEL_LINK}**

🏠 **العودة للواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")],
                [InlineKeyboardButton("🛒 تصفح العروض", callback_data="browse_offers")]
            ]),
            parse_mode='Markdown'
        )
        
        del user_states[user_id]
        
        for key in ['awaiting_price', 'awaiting_min_amount', 'awaiting_max_amount', 'creating_sell_offer', 'creating_buy_offer']:
            if key in context.user_data:
                del context.user_data[key]
        
    except Exception as e:
        logging.error(f"خطأ في حفظ العرض: {e}")
        await query.edit_message_text(
            "❌ **حدث خطأ في حفظ العرض. يرجى المحاولة لاحقاً.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 المحاولة مجدداً", callback_data="sell_crypto_offer" if state.offer_type == "بيع" else "buy_crypto_offer")]
            ]),
            parse_mode='Markdown'
        )

# ============ معالجة طلبات المسؤول ============
async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("approve_payment_"):
        user_id = int(data.split("_")[2])
        
        db = DatabaseManager()
        db.set_paid_entry_fee(user_id)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="""🎉 **مبروك! تم تفعيل حسابك بنجاح!**

✅ **تم قبول إثبات الدفع وتم تفعيل حسابك.**
💰 **الآن يمكنك:**
• نشر عروض شراء جديدة
• أخذ عروض بيع متاحة
• استخدام جميع مزايا البوت

🚀 **ابدأ الآن واستفد من خدماتنا!**

👇 **من الواجهة الرئيسية:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال رسالة للمستخدم: {e}")
        
        await query.edit_message_caption(
            caption=f"✅ **تم قبول وتفعيل حساب المستخدم {user_id}**\n\n"
                   f"📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )
        
    elif data.startswith("reject_payment_"):
        user_id = int(data.split("_")[2])
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="""⚠️ **تم رفض إثبات الدفع**

❌ **للأسف، لم يتم قبول إثبات الدفع الذي أرسلته.**

🔍 **الأسباب المحتملة:**
• الصورة غير واضحة
• المعلومات غير مكتملة
• المبلغ غير صحيح

💡 **يمكنك:**
1. إعادة المحاولة بإرسال صورة أوضح
2. التواصل مع الدعم للاستفسار

📞 **للدعم والمساعدة:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 الدعم الفني", url=f"tg://resolve?domain={SUPPORT_USERNAME[1:]}")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال رسالة للمستخدم: {e}")
        
        await query.edit_message_caption(
            caption=f"❌ **تم رفض طلب المستخدم {user_id}**\n\n"
                   f"📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )

async def confirm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id in user_states:
        del user_states[user_id]
    
    if user_id in user_transactions:
        del user_transactions[user_id]
    
    if user_id in editing_offers:
        del editing_offers[user_id]
    
    for key in ['awaiting_price', 'awaiting_min_amount', 'awaiting_max_amount', 
               'creating_sell_offer', 'creating_buy_offer', 'waiting_payment_proof',
               'awaiting_transaction_amount', 'awaiting_payment_method']:
        if key in context.user_data:
            del context.user_data[key]
    
    await query.edit_message_text(
        "❌ **تم إلغاء العملية**\n\n"
        "🏠 **العودة للواجهة الرئيسية:**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
        ]),
        parse_mode='Markdown'
    )

async def cancel_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in user_states:
        await query.edit_message_text("❌ انتهت الجلسة. يرجى البدء من جديد.")
        return
    
    state = user_states[user_id]
    await show_payment_methods(update, context)

# ============ الملف الشخصي ============
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    user = update.effective_user
    db = DatabaseManager()
    
    user_info = db.get_user_info(user.id)
    if not user_info:
        db.set_paid_entry_fee(user.id)
        user_info = db.get_user_info(user.id)
    
    has_paid = db.has_paid_entry_fee(user.id)
    payment_status = "✅ مدفوع" if has_paid else "❌ غير مدفوع"
    
    if user_info:
        user_id, username, first_name, phone_number, contact_info, join_date, reputation, is_banned, ban_reason, total_transactions, completed_transactions, completion_rate, user_level, accepted_terms, joined_channel, registration_step = user_info
    else:
        total_transactions = 0
        completed_transactions = 0
        completion_rate = 0.0
        user_level = "جديد"
        phone_number = "غير مسجل"
        contact_info = "غير مسجل"
    
    completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
    registration_status = "✅ مسجل بالكامل" if db.is_user_registered(user.id) else "❌ غير مكتمل"
    
    profile_text = f"""
📁 **ملفي الشخصي**

👤 **المعلومات الأساسية:**
• 🆔 **رقم المعرف:** `{user.id}`
• 👤 **اسم المستخدم:** {f'@{user.username}' if user.username else 'غير محدد'}
• 📞 **رقم الهاتف:** {phone_number or 'غير مسجل'}
• 📱 **معلومات الاتصال:** {contact_info or 'غير مسجل'}
• 🏆 **المستوى:** {user_level}
• 📅 **تاريخ الانضمام:** {join_date[:10] if user_info else datetime.now().strftime('%Y-%m-%d')}
• ✅ **حالة التسجيل:** {registration_status}
• 💰 **رسوم الدخول:** {payment_status}

📊 **إحصائياتي:**
• 📈 **إجمالي الصفقات:** {total_transactions}
• ✅ **الصفقات المكتملة:** {completed_transactions}
• 📊 **نسبة الإتمام:** {completion_rate_display}%
• ⭐ **السمعة:** {reputation if user_info else 100}

🎯 **اختر ما تريد معرفته عن حسابك:**
    """
    
    keyboard = [
        [InlineKeyboardButton("💰 التوفير", callback_data="profile_savings")],
        [InlineKeyboardButton("🏆 برنامج النقاط الذهبية", callback_data="profile_points")],
        [InlineKeyboardButton("⭐ سمعتي", callback_data="profile_reputation")],
        [InlineKeyboardButton("🎁 العمليات المجانية", callback_data="profile_free_transactions")],
        [InlineKeyboardButton("📋 سجل العمليات", callback_data="profile_history")],
        [InlineKeyboardButton("🤝 رابط الإحالة", callback_data="profile_referral")],
        [InlineKeyboardButton("📍 العناوين المحفوظة", callback_data="profile_addresses")],
        [InlineKeyboardButton("🏠 العودة للواجهة الرئيسية", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        profile_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ التنبيهات ============
async def notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    notifications_text = """
🔔 **إدارة التنبيهات**

📊 **إحصائياتك:**
• التنبيهات النشطة: 0/3
• تم تفعيلها: 0

✨ **ما يمكنك فعلا:**
• إضافة تنبيه جديد
• عرض التنبيهات النشطة
• إلغاء التنبيهات

💡 **نصائح:**
• يمكنك إضافة حتى 3 تنبيهات نشطة
• التنبيهات تبقى نشطة حتى بعد التفعيل
• سيتم إشعارك عند توفر عروض تناسب معاييرك
    """
    
    keyboard = [
        [InlineKeyboardButton("👁️ عرض التنبيهات", callback_data="view_notifications")],
        [InlineKeyboardButton("➕ إضافة تنبيه جديد", callback_data="add_notification")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        notifications_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ الدعم والمساعدة ============
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    support_text = f"""
❓ **الدعم والمساعدة**

🛠️ **كيف يمكننا مساعدتك؟**
• مشاكل تقنية في استخدام البوت
• استفسارات حول العمليات
• شكاوى أو اقتراحات
• مشاكل في التحويلات

📞 **طرق التواصل:**
• الدردشة المباشرة مع الدعم
• البريد الإلكتروني
• قناة التليجرام الرسمية

⏰ **أوقات الدعم:** 24/7
⚡ **سرعة الرد:** خلال 15 دقيقة
    """
    
    keyboard = [
        [InlineKeyboardButton("💬 الدردشة المباشرة", url=f"tg://resolve?domain={SUPPORT_USERNAME[1:]}")],
        [InlineKeyboardButton("📢 القناة الرسمية", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        support_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ شروط الاستخدام ============
async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    terms_text = """
📜 **شروط استخدام QuickCashSY**

🌟 **مرحباً بك في QuickCashSY!** باستخدام هذا البوت، فإنك توافق على الالتزام بالشروط والأحكام التالية. يرجى قراءتها بعناية.

**1. القبول بالشروط**
باستخدامك لـ **QuickCashSY**، فإنك تقر بأنك قرأت وفهمت ووافقت على الالتزام بجميع الشروط والأحكام الواردة هنا. إذا لم توافق على أي جزء من هذه الشروط، فلا يجوز لك استخدام البوت.

**2. طبيعة الخدمة**
**QuickCashSY** هو بوت يقدم خدمة شخص لشخص (P2P) لعمليات بيع وشراء عملة الـ USDT. نحن نقوم بالربط بين طرفي المعاملة لضمان حقوقهما.

⚡ **آلية عملنا:**
1. نستلم رصيد USDT من البائع
2. ننتظر أن يقوم الطرف الآخر (المشتري) بإرسال القيمة المتفق عليها
3. بعد تأكيد وصول حق الطرف الأول كاملاً، نقوم بإرسال رصيد USDT للطرف الثاني
4. هنا تنتهي مهمتنا كوسيط

⚠️ **نُعلمك بأننا غير مسؤولين عن أي طرف ثالث آخر قد يتدخل في المعاملة خارج نطاق خدمتنا.**

**3. استخدام البوت**
✅ **الاستخدام المشروع:** يجب استخدام البوت بطريقة قانونية ومسؤولة.
📋 **المحتوى:** أنت مسؤول بالكامل عن أي محتوى أو معلومات تقوم بتقديمها.

🚫 **السلوك المحظور:**
• نشر أو إرسال أي محتوى غير قانوني أو مسيء
• التحرش أو المطاردة أو الإضرار بأي شخص
• انتحال شخصية أي كيان أو فرد
• نشر عروض وهمية أو كاذبة
• استغلال البوت لأغراض تجارية غير مصرح بها

⚠️ **أي ملاحظة أو دليل على ذلك سيعرضك للحظر الفوري.**

**4. الخصوصية**
نحن نلتزم بحماية خصوصيتك. يتم التعامل مع بياناتك بأقصى درجات السرية والأمان.

**5. إخلاء المسؤولية**
يتم تقديم البوت "كما هو" و"حسب توفره". نحن لا نضمن أن البوت سيكون خاليًا من الأخطاء.

**6. حدود المسؤولية**
لن نكون مسؤولين عن أي أضرار تنشأ عن استخدامك أو عدم قدرتك على استخدام البوت.

**7. التعديلات على الشروط**
نحتفظ بالحق في تعديل شروط الاستخدام هذه في أي وقت. استمرارك في الاستخدام يعني موافقتك على التعديلات.

**8. الإنهاء**
يجوز لنا تعليق أو إنهاء وصولك إلى البوت في أي وقت، دون إشعار مسبق، لأي سبب.

---

🔥 **فريق QuickCashSY**
💎 **وسيطك الموثوق للبيع والشراء**
    """
    
    keyboard = [
        [InlineKeyboardButton("✅ أوافق على الشروط", callback_data="accept_terms")],
        [InlineKeyboardButton("🏠 العودة للواجهة", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        terms_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ الأزرار الأخرى ============
async def accept_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer("✅ تم قبول شروط الاستخدام", show_alert=True)
    
    await query.edit_message_text(
        "🎉 **شكراً لقبولك شروط الاستخدام!**\n\n"
        "✅ **يمكنك الآن استخدام جميع خدمات QuickCashSY**\n\n"
        "👇 **ابدأ من هنا:**",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")
        ]]),
        parse_mode='Markdown'
    )

async def complete_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "🔗 **إكمال عملية الربط**\n\n"
        "📱 **لإكمال ربط حسابك، يرجى:**\n\n"
        "1. إضافة معلومات الدفع الخاصة بك\n"
        "2. تأكيد رقم الهاتف\n"
        "3. إضافة وسائل التواصل\n\n"
        "⚡ **سيتم توجيهك للخطوات اللازمة**",
        parse_mode='Markdown'
    )

async def view_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "👁️ **التنبيهات النشطة**\n\n"
        "📊 **لا توجد تنبيهات نشطة حالياً**\n\n"
        "➕ **يمكنك إضافة تنبيه جديد من الزر أدناه**",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ إضافة تنبيه", callback_data="add_notification"),
            InlineKeyboardButton("🔙 رجوع", callback_data="notifications")
        ]]),
        parse_mode='Markdown'
    )

async def add_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    if is_banned:
        await query.answer("🚫 تم حظر حسابك", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "➕ **إضافة تنبيه جديد**\n\n"
        "🔔 **حدد معايير التنبيه:**\n\n"
        "1. **نوع العملية:** شراء/بيع\n"
        "2. **السعر المطلوب:**\n"
        "3. **الكمية:**\n"
        "4. **طريقة الدفع:**\n\n"
        "⚡ **سيتم توجيهك لإنشاء التنبيه**",
        parse_mode='Markdown'
    )

# ============ دالة إرسال إشعار اكتمال التسجيل ============
async def send_contact_registration_complete(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """إرسال إشعار اكتمال التسجيل للمستخدم"""
    try:
        await asyncio.sleep(0.5)
        
        await context.bot.send_message(
            chat_id=user_id,
            text="""✨ **مرحباً بك في مجتمع QuickCashSY!**

✅ **تم تفعيل حسابك بنجاح**

🎯 **الآن يمكنك:**
• 🛒 تصفح العروض المتاحة للبيع والشراء
• 💎 إنشاء عروضك الخاصة
• 📊 إدارة ملفك الشخصي والمعاملات
• 🔔 الحصول على تنبيهات بالعروض الجديدة

💰 **استفد من فرص تداول USDT بأمان وسهولة**

👇 **ابدأ الآن من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")],
                [InlineKeyboardButton("🛒 تصفح العروض", callback_data="browse_offers")]
            ]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار اكتمال التسجيل: {e}")

# ============ معالجة أزرار ReplyKeyboardMarkup ============
async def handle_reply_keyboard_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار ReplyKeyboardMarkup"""
    user_id = update.effective_user.id
    
    if update.message.text == "📱 مشاركة جهة الاتصال":
        db = DatabaseManager()
        registration_step = db.get_user_registration_step(user_id)
        
        if registration_step == 'contact_registration':
            contact_message = await update.message.reply_text(
                "📱 **لمشاركة جهة اتصالك:**\n\n"
                "⬇️ **اضغط على الزر أدناه:**",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("📱 مشاركة جهة الاتصال", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                ),
                parse_mode='Markdown'
            )
            
            context.user_data['contact_request_message_id'] = contact_message.message_id
        else:
            await update.message.reply_text(
                "⚠️ **أنت لا توجد في مرحلة تسجيل جهة الاتصال**\n\n"
                "🔙 **يرجى البدء من البداية:**",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
    
    else:
        await update.message.reply_text(
            "⚠️ **الزر غير معروف**",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )

# ============ معالجة الأزرار الرئيسية (الجديدة والمحدثة) ============
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(query.from_user.id)
    
    data = query.data
    
    if query.from_user.id != ADMIN_ID and is_banned:
        allowed_buttons = ['back_to_main', 'support', 'accept_terms', 'view_buy_offers', 'view_sell_offers', 
                          'accept_terms_step', 'check_channel_membership', 'share_contact', 'my_requests']
        if not any(data.startswith(btn) for btn in allowed_buttons):
            await query.answer("🚫 تم حظر حسابك", show_alert=True)
            return
    
    await query.answer()
    
    # ============ معالجة أزرار التسجيل ============
    if data == "accept_terms_step":
        await accept_terms_step(update, context)
        return
    elif data == "check_channel_membership":
        await check_channel_membership_handler(update, context)
        return
    elif data == "share_contact":
        user_id = query.from_user.id
        
        db = DatabaseManager()
        is_banned, ban_reason = db.is_user_banned(user_id)
        if is_banned:
            await query.answer("🚫 تم حظر حسابك", show_alert=True)
            return
        
        await query.answer("📱 جاهز لمشاركة جهة الاتصال")
        
        await query.edit_message_text(
            "📱 **مشاركة جهة الاتصال**\n\n"
            "👇 **سيظهر لك الآن زر لمشاركة جهة الاتصال.**\n\n"
            "**ما عليك سوى:**\n"
            "1. الضغط على الزر الذي سيظهر\n"
            "2. اختيار جهة اتصالك من قائمة تليجرام\n"
            "3. الموافقة على المشاركة\n\n"
            "✅ **سيتم تسجيل معلوماتك تلقائياً بنقرة واحدة!**",
            parse_mode='Markdown'
        )
        
        await asyncio.sleep(0.5)
        
        try:
            contact_message = await context.bot.send_message(
                chat_id=user_id,
                text="📱 **لمشاركة جهة اتصالك:**\n\n"
                     "⬇️ **اضغط على الزر أدناه:**",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("📱 مشاركة جهة الاتصال", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                ),
                parse_mode='Markdown'
            )
            
            context.user_data['contact_request_message_id'] = contact_message.message_id
            
        except Exception as e:
            logging.error(f"خطأ في إرسال زر مشاركة جهة الاتصال: {e}")
            await query.edit_message_text(
                "❌ **حدث خطأ في إعداد مشاركة جهة الاتصال**\n\n"
                "⚠️ **يرجى المحاولة مرة أخرى:**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 المحاولة مرة أخرى", callback_data="share_contact")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="contact_registration_back")]
                ]),
                parse_mode='Markdown'
            )
        return
    
    if data == "contact_registration_back":
        await show_contact_registration_step(update, context)
        return
    
    # ============ معالجة أزرار إدارة العروض الجديدة ============
    if data.startswith("manage_offer_"):
        offer_id = int(data.split("_")[2])
        await manage_specific_offer(update, context, offer_id)
        return
    
    elif data.startswith("edit_offer_"):
        offer_id = int(data.split("_")[2])
        await start_edit_offer(update, context, offer_id)
        return
    
    elif data.startswith("delete_offer_"):
        offer_id = int(data.split("_")[2])
        await delete_offer_confirmation(update, context, offer_id)
        return
    
    elif data.startswith("confirm_delete_"):
        offer_id = int(data.split("_")[2])
        await confirm_delete_offer(update, context, offer_id)
        return
    
    elif data.startswith("save_edit_"):
        offer_id = int(data.split("_")[2])
        await save_offer_edit(update, context, offer_id)
        return
    
    elif data.startswith("edit_"):
        await handle_edit_payment_selection(update, context)
        return
    
    elif data == "edit_payment_done":
        await confirm_offer_edit(update, context)
        return
    
    elif data == "edit_cancel":
        user_id = query.from_user.id
        if user_id in editing_offers:
            offer_id = editing_offers[user_id]['offer_id']
            del editing_offers[user_id]
            await manage_specific_offer(update, context, offer_id)
        return
    
    # ============ معالجة أزرار طلبات المستخدم الجديدة ============
    elif data == "my_requests":
        await my_requests(update, context)
        return
    
    elif data.startswith("manage_request_"):
        transaction_id = int(data.split("_")[2])
        await manage_specific_request(update, context, transaction_id)
        return
    
    elif data.startswith("cancel_request_"):
        transaction_id = int(data.split("_")[2])
        await cancel_user_request(update, context, transaction_id)
        return
    
    # ============ معالجة أزرار الموافقة على الطلبات ============
    elif data.startswith("seller_approve_"):
        transaction_id = int(data.split("_")[2])
        await handle_seller_approval(update, context, transaction_id, approve=True)
        return
    
    elif data.startswith("seller_reject_"):
        transaction_id = int(data.split("_")[2])
        await handle_seller_approval(update, context, transaction_id, approve=False)
        return
    
    # ============ معالجة أزرار العروض الأساسية ============
    if data.startswith("view_offer_"):
        offer_id = data.split("_")[2]
        await show_offer_details_from_callback(update, context, offer_id)
        return
    elif data.startswith("contact_seller_"):
        offer_id = data.split("_")[2]
        await contact_seller(update, context, offer_id)
        return
    elif data.startswith("start_purchase_"):
        offer_id = data.split("_")[2]
        await start_purchase(update, context, offer_id)
        return
    elif data.startswith("select_payment_"):
        await handle_payment_selection(update, context)
        return
    elif data == "confirm_transaction":
        await confirm_transaction(update, context)
        return
    elif data.startswith("filter_category_"):
        await handle_category_selection(update, context)
    elif data.startswith("sort_"):
        await handle_sort_order(update, context)
    elif data.startswith("page_"):
        await handle_page_navigation(update, context)
    elif data in ["payment_done", "payment_cancel", "payment_harm", "payment_harm_usd", 
                 "payment_fouad", "payment_fouad_usd", "payment_shkhashiro", "payment_shkhashiro_usd",
                 "payment_mtn_cash", "payment_syriatel_cash", "payment_sham_cash", "payment_sham_cash_usd",
                 "payment_qadmous"]:
        await handle_payment_selection_offer(update, context)
    elif data == "publish_offer":
        await publish_offer(update, context)
    elif data == "confirm_cancel":
        await confirm_cancel(update, context)
    elif data == "cancel_cancel":
        await cancel_cancel(update, context)
    
    # ============ معالجة أزرار إدارة العروض حسب النوع ============
    elif data == "my_active_offers":
        await show_user_offers_list(update, context, "active")
        return
    elif data == "my_pending_offers":
        await show_user_offers_list(update, context, "pending")
        return
    elif data == "my_completed_offers":
        await show_user_offers_list(update, context, "completed")
        return
    elif data == "my_all_offers":
        await show_user_offers_list(update, context, "all")
        return
    
    # ============ معالجة أزرار المسؤول ============
    elif data == "admin_panel":
        await admin_panel(update, context)
    elif data == "admin_review_offers":
        await admin_review_offers(update, context)
    elif data == "admin_next_pending":
        await admin_next_pending(update, context)
    elif data.startswith("admin_approve_"):
        await admin_approve_offer(update, context)
    elif data.startswith("admin_reject_"):
        await admin_reject_offer(update, context)
    elif data.startswith("admin_view_user_"):
        user_id = int(data.split("_")[3])
        await admin_manage_specific_user(update, context)
    elif data == "admin_manage_users":
        await admin_manage_users(update, context)
    elif data.startswith("admin_manage_user_"):
        await admin_manage_specific_user(update, context)
    elif data.startswith("admin_ban_"):
        await admin_ban_user(update, context)
    elif data.startswith("admin_unban_"):
        await admin_unban_user(update, context)
    elif data.startswith("admin_message_"):
        await admin_message_user(update, context)
    elif data == "admin_broadcast":
        await admin_broadcast(update, context)
    elif data == "admin_active_offers":
        await admin_active_offers(update, context)
    elif data == "admin_statistics":
        await admin_statistics(update, context)
    elif data == "admin_registration_stats":
        await admin_registration_stats(update, context)
    elif data == "admin_charts":
        await query.answer("🚧 هذه الميزة قيد التطوير", show_alert=True)
    elif data.startswith("admin_search_"):
        await query.answer("🚧 هذه الميزة قيد التطوير", show_alert=True)
    elif data.startswith("admin_user_offers_"):
        user_id = int(data.split("_")[3])
        await query.answer(f"🚧 عروض المستخدم #{user_id} قيد التطوير", show_alert=True)
    elif data.startswith("admin_complete_registration_"):
        await admin_complete_registration(update, context)
        return
    elif data == "admin_review_transactions":
        await admin_review_transactions(update, context)
    elif data.startswith("admin_approve_transaction_"):
        transaction_id = int(data.split("_")[3])
        await admin_approve_transaction(update, context, transaction_id)
    elif data.startswith("admin_reject_transaction_"):
        transaction_id = int(data.split("_")[3])
        await admin_reject_transaction(update, context, transaction_id)
    elif data.startswith("admin_view_transaction_"):
        transaction_id = int(data.split("_")[3])
        await admin_view_transaction(update, context, transaction_id)
    elif data == "admin_next_transaction":
        await admin_next_transaction(update, context)
    
    # ============ معالجة الأزرار الرئيسية ============
    elif data == "view_buy_offers":
        await view_buy_offers(update, context)
    elif data == "view_sell_offers":
        await view_sell_offers(update, context)
    elif data == "my_offers":
        await my_offers(update, context)
    elif data == "back_to_main":
        user_id = query.from_user.id
        if user_id in user_states:
            del user_states[user_id]
        if user_id in user_transactions:
            del user_transactions[user_id]
        if user_id in offer_filters:
            del offer_filters[user_id]
        if user_id in editing_offers:
            del editing_offers[user_id]
        
        for key in ['awaiting_price', 'awaiting_min_amount', 'awaiting_max_amount', 
                   'creating_sell_offer', 'creating_buy_offer', 'waiting_payment_proof',
                   'pending_offers_index', 'pending_offers_list', 'awaiting_contact_info',
                   'awaiting_transaction_amount', 'awaiting_payment_method']:
            if key in context.user_data:
                del context.user_data[key]
        
        db = DatabaseManager()
        if not db.is_user_registered(user_id):
            await show_terms_step(update, context)
        else:
            await start_from_query(query, context)
    elif data == "browse_offers":
        await browse_offers(update, context)
    elif data == "create_offer":
        await create_offer(update, context)
    elif data == "my_profile":
        await my_profile(update, context)
    elif data == "notifications":
        await notifications(update, context)
    elif data == "support":
        await support(update, context)
    elif data == "terms":
        await terms(update, context)
    elif data == "sell_crypto_offer":
        await sell_crypto_offer(update, context)
    elif data == "buy_crypto_offer":
        await buy_crypto_offer(update, context)
    elif data == "accept_terms":
        await accept_terms(update, context)
    elif data == "complete_linking":
        await complete_linking(update, context)
    elif data == "view_notifications":
        await view_notifications(update, context)
    elif data == "add_notification":
        await add_notification(update, context)
    elif data.startswith("buy_offer_") or data.startswith("sell_offer_"):
        offer_id = data.split("_")[2]
        await show_offer_details_from_callback(update, context, offer_id)
    elif data.startswith("profile_"):
        await query.answer("🚧 هذه الميزة قيد التطوير", show_alert=True)
    elif data == "noop":
        await query.answer("")

async def handle_edit_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in editing_offers:
        await query.edit_message_text("❌ انتهت جلسة التعديل. يرجى البدء من جديد.")
        return
    
    editing_state = editing_offers[user_id]
    
    payment_methods_map = {
        "edit_payment_harm": "الهرم",
        "edit_payment_harm_usd": "الهرم (دولار)",
        "edit_payment_fouad": "الفؤاد",
        "edit_payment_fouad_usd": "الفؤاد (دولار)",
        "edit_payment_shkhashiro": "شخاشيرو",
        "edit_payment_shkhashiro_usd": "شخاشيرو (دولار)",
        "edit_payment_mtn_cash": "ام تي ان كاش",
        "edit_payment_syriatel_cash": "سيريتل كاش",
        "edit_payment_sham_cash": "شام كاش",
        "edit_payment_sham_cash_usd": "شام كاش (دولار)",
        "edit_payment_qadmous": "القدموس"
    }
    
    if data in payment_methods_map:
        method = payment_methods_map[data]
        
        if method in editing_state['payment_methods']:
            editing_state['payment_methods'].remove(method)
        else:
            editing_state['payment_methods'].append(method)
        
        await update_edit_payment_keyboard(query, editing_state)

async def update_edit_payment_keyboard(query, editing_state):
    payment_methods = [
        ("الهرم", "edit_payment_harm"),
        ("الهرم (دولار)", "edit_payment_harm_usd"),
        ("الفؤاد", "edit_payment_fouad"),
        ("الفؤاد (دولار)", "edit_payment_fouad_usd"),
        ("شخاشيرو", "edit_payment_shkhashiro"),
        ("شخاشيرو (دولار)", "edit_payment_shkhashiro_usd"),
        ("ام تي ان كاش", "edit_payment_mtn_cash"),
        ("سيريتل كاش", "edit_payment_syriatel_cash"),
        ("شام كاش", "edit_payment_sham_cash"),
        ("شام كاش (دولار)", "edit_payment_sham_cash_usd"),
        ("القدموس", "edit_payment_qadmous")
    ]
    
    keyboard = []
    for method_name, callback_data in payment_methods:
        if method_name in editing_state['payment_methods']:
            button_text = f"✓ {method_name}"
        else:
            button_text = method_name
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([
        InlineKeyboardButton("✅ انتهى", callback_data="edit_payment_done"),
        InlineKeyboardButton("❌ إلغاء التعديل", callback_data="edit_cancel")
    ])
    
    selected_methods = "\n".join([f"• {method}" for method in editing_state['payment_methods']]) if editing_state['payment_methods'] else "لم يتم اختيار أي طريقة بعد"
    
    await query.edit_message_text(
        f"""✅ **تفاصيل العرض المعدل:**

📊 **نوع العرض :** {editing_state['offer_type']}
💰 **السعر الجديد :** {editing_state['price']:,.2f} ليرة/USDT
🔢 **الحد الأدنى الجديد :** {editing_state['min_amount']} USDT
🔢 **الحد الأقصى الجديد :** {editing_state['max_amount']} USDT

💳 **طرق الدفع المختارة:**
{selected_methods}

👇 **اختر طرق الدفع المناسبة:**""",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_offer_details_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, first_name, reputation, completion_rate, total_transactions, completed_transactions, user_level = offer
    
    if status != 'active':
        await query.answer("❌ هذا العرض غير متاح حالياً", show_alert=True)
        return
    
    username_display = f"@{username}" if username else first_name or f"المستخدم {user_id}"
    offer_type_arabic = "بيع" if offer_type == "بيع" else "شراء"
    payment_methods = payment_method.split(',')
    
    avg_amount = (min_amount + max_amount) / 2
    commission = avg_amount * COMMISSION_RATE
    completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
    offer_emoji = "🔴" if offer_type == "بيع" else "🟢"
    
    offer_details = f"""
{offer_emoji} **تفاصيل العرض #{offer_id}**

📋 **معلومات العرض:**
┌ 📊 **النوع:** {offer_emoji} {offer_type_arabic} USDT
├ 💰 **السعر:** {price:,.2f} ليرة/USDT
├ 📦 **الكمية:** {min_amount} - {max_amount} USDT
├ ⏳ **المدة:** {transaction_duration} دقيقة
└ 📅 **النشر:** {created_at[:16]}

👤 **معلومات التاجر:**
┌ 🏷️ **الاسم:** {username_display}
├ 🏆 **المستوى:** {user_level}
├ 📊 **نسبة الإتمام:** {completion_rate_display}%
├ ⭐ **السمعة:** {reputation:.1f}
└ 📈 **الصفقات:** {total_transactions} ({completed_transactions} مكتملة)

💳 **طرق الدفع المتاحة:**
"""
    
    for i, method in enumerate(payment_methods, 1):
        offer_details += f"**{i}. {method}**\n"
    
    offer_details += f"""
📉 **عمولة الوسيط:** {commission:.2f}$ / {avg_amount:.0f}$

💡 **للإتمام الصفقة، اتبع الخطوات التالية:**
1. تأكد من توفر المبلغ المطلوب
2. قم بالتواصل مع البائع
3. استخدم وسيط موثوق للمعاملة
4. احتفظ بسجلات الدفع
"""
    
    keyboard = []
    
    if offer_type == "بيع":
        keyboard.append([InlineKeyboardButton("🛒 شراء هذا العرض", callback_data=f"start_purchase_{offer_id}")])
    else:
        keyboard.append([InlineKeyboardButton("💰 البيع لهذا العرض", callback_data=f"start_purchase_{offer_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("🔍 تصفح عروض أخرى", callback_data="browse_offers")],
        [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
    ])
    
    await query.edit_message_text(
        offer_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def contact_seller(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    query = update.callback_query
    
    db = DatabaseManager()
    if not db.is_user_registered(query.from_user.id):
        await query.answer("⚠️ يجب إكمال التسجيل أولاً", show_alert=True)
        await show_terms_step(update, context)
        return
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, first_name, reputation, completion_rate, total_transactions, completed_transactions, user_level = offer
    
    username_display = f"@{username}" if username else first_name or f"المستخدم {user_id}"
    offer_type_arabic = "بيع" if offer_type == "بيع" else "شراء"
    completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
    
    contact_text = f"""
🤝 **الاتصال بالبائع**

📋 **معلومات الاتصال:**
• **رقم العرض:** #{offer_id}
• **نوع العرض:** {offer_type_arabic}
• **البائع:** {username_display}
• **المستوى:** {user_level}
• **السعر:** {price:,.2f} ليرة/USDT
• **الكمية:** {min_amount} - {max_amount} USDT
• **نسبة الإتمام:** {completion_rate_display}% ({total_transactions} صفقات)

💡 **نصائح للتواصل الآمن:**
1. تأكد من هوية الطرف الآخر
2. استخدم وسيط موثوق للمعاملة
3. احتفظ بسجلات الدفع
4. لا تشارك معلوماتك الشخصية الحساسة

⚠️ **تحذير:** QuickCashSY ليس مسؤولاً عن أي معاملات تتم خارج النظام.
"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 العودة للعرض", callback_data=f"view_offer_{offer_id}")],
        [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        contact_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def start_from_query(query, context):
    user = query.from_user
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(user.id)
    
    if is_banned and user.id != ADMIN_ID:
        await query.edit_message_text(
            f"🚫 **تم حظر حسابك**\n\n"
            f"**السبب:** {ban_reason}\n\n"
            f"للاستفسار، تواصل مع الدعم: {SUPPORT_USERNAME}",
            parse_mode='Markdown'
        )
        return
    
    if not db.is_user_registered(user.id):
        await show_terms_step(update, context)
        return
    
    user_name = f"@{user.username}" if user.username else user.first_name
    
    welcome_text = f"""
🌟 **مرحباً بك {user_name} في مجتمع QuickCashSY للوساطة المالية** 🌟

💎 **منصتك الآمنة للبيع والشراء**

✨ **ماذا يمكن أن نقوم به سوياً؟**
🚀 انشر عرضك الخاص للبيع والشراء
💫 تصفح العروض المتاحة واستفد من الفرص
📈 إدارة معاملاتك بذكاء وأكثر كفاءة

💰 **ابدأ معاملاتك واختر ما يناسبك من الخيارات المتاحة التالية:**
    """
    
    keyboard = [
        [
            InlineKeyboardButton("🛒 تصفح العروض", callback_data="browse_offers"),
            InlineKeyboardButton("💎 إنشاء عرض", callback_data="create_offer")
        ],
        [
            InlineKeyboardButton("📁 ملفي الشخصي", callback_data="my_profile"),
            InlineKeyboardButton("📊 إدارة عروضي", callback_data="my_offers")
        ],
        [
            InlineKeyboardButton("🔄 طلباتي", callback_data="my_requests"),
            InlineKeyboardButton("🔔 التنبيهات", callback_data="notifications")
        ],
        [
            InlineKeyboardButton("❓ الدعم", callback_data="support"),
            InlineKeyboardButton("📜 الشروط", callback_data="terms")
        ]
    ]
    
    if user.id == ADMIN_ID:
        keyboard.insert(0, [InlineKeyboardButton("🛠️ لوحة التحكم", callback_data="admin_panel")])
    
    await query.edit_message_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ لوحة تحكم المسؤول ============
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    
    pending_offers = db.get_pending_offers()
    active_offers = db.get_active_offers()
    all_users = db.get_all_users()
    banned_count = sum(1 for user in all_users if user[5] == 1)
    notifications_count = db.get_unread_notifications_count()
    
    pending_transactions = db.get_pending_transactions()
    pending_transactions_count = len(pending_transactions)
    
    pending_approval_transactions = db.get_pending_approval_transactions()
    pending_approval_count = len(pending_approval_transactions)
    
    registered_users = sum(1 for user in all_users if db.is_user_registered(user[0]))
    
    admin_text = f"""
🛠️ **لوحة تحكم المسؤول**

📊 **الإحصائيات:**
├ 📝 العروض المنتظرة: {len(pending_offers)}
├ ⏳ طلبات موافقة: {pending_approval_count}
├ 💰 المعاملات المنتظرة: {pending_transactions_count}
├ ✅ العروض النشطة: {len(active_offers)}
├ 👥 إجمالي المستخدمين: {len(all_users)}
├ ✅ المسجلين بالكامل: {registered_users}
├ 🚫 المستخدمين المحظورين: {banned_count}
└ 🔔 الإشعارات غير المقروءة: {notifications_count}

🔧 **أدوات التحكم:**
    """
    
    keyboard = [
        [InlineKeyboardButton("📝 مراجعة العروض المنتظرة", callback_data="admin_review_offers")],
        [InlineKeyboardButton("⏳ مراجعة طلبات الموافقة", callback_data="admin_review_pending_approvals")],
        [InlineKeyboardButton("💰 مراجعة المعاملات المنتظرة", callback_data="admin_review_transactions")],
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_manage_users")],
        [InlineKeyboardButton("📢 بث رسالة عامة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📋 العروض النشطة", callback_data="admin_active_offers")],
        [InlineKeyboardButton("📊 الإحصائيات الكاملة", callback_data="admin_statistics")],
        [InlineKeyboardButton("🏠 العودة للواجهة الرئيسية", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_review_pending_approvals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    pending_transactions = db.get_pending_approval_transactions()
    
    if not pending_transactions:
        await query.edit_message_text(
            "⏳ **مراجعة طلبات الموافقة**\n\n"
            "✅ **لا توجد طلبات موافقة منتظرة حالياً**\n\n"
            "🔙 **العودة للوحة التحكم:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    transaction = pending_transactions[0]
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, seller_username, offer_type = transaction
    
    buyer_display = f"@{buyer_username}" if buyer_username else f"المشتري {buyer_id}"
    seller_display = f"@{seller_username}" if seller_username else f"البائع {seller_id}"
    
    transaction_details = f"""
⏳ **طلب موافقة #{transaction_id} - بانتظار موافقة البائع**

📋 **تفاصيل الطلب:**
├ 📊 **النوع:** {offer_type}
├ 💰 **الكمية:** {amount} USDT
├ 📈 **السعر:** {price:,.2f} ليرة/USDT
├ 💵 **المجموع:** {total_price:,.2f} ليرة
├ 💳 **طريقة الدفع:** {payment_method}
├ 👤 **المشتري:** {buyer_display}
├ 👤 **البائع:** {seller_display}
└ 📅 **تاريخ الطلب:** {created_at[:16]}

💡 **هذا الطلب بانتظار موافقة البائع.**
"""
    
    keyboard = [
        [InlineKeyboardButton("👁️ عرض تفاصيل كاملة", callback_data=f"admin_view_transaction_{transaction_id}")],
        [
            InlineKeyboardButton("⏭️ التالي", callback_data="admin_next_pending_approval"),
            InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
        ]
    ]
    
    context.user_data['pending_approvals_index'] = 0
    context.user_data['pending_approvals_list'] = pending_transactions
    
    await query.edit_message_text(
        transaction_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_next_pending_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    if 'pending_approvals_index' not in context.user_data or 'pending_approvals_list' not in context.user_data:
        await admin_review_pending_approvals(update, context)
        return
    
    current_index = context.user_data['pending_approvals_index'] + 1
    pending_transactions = context.user_data['pending_approvals_list']
    
    if current_index >= len(pending_transactions):
        current_index = 0
    
    context.user_data['pending_approvals_index'] = current_index
    transaction = pending_transactions[current_index]
    
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, seller_username, offer_type = transaction
    
    buyer_display = f"@{buyer_username}" if buyer_username else f"المشتري {buyer_id}"
    seller_display = f"@{seller_username}" if seller_username else f"البائع {seller_id}"
    
    transaction_details = f"""
⏳ **طلب موافقة #{transaction_id} - بانتظار موافقة البائع ({current_index + 1}/{len(pending_transactions)})**

📋 **تفاصيل الطلب:**
├ 📊 **النوع:** {offer_type}
├ 💰 **الكمية:** {amount} USDT
├ 📈 **السعر:** {price:,.2f} ليرة/USDT
├ 💵 **المجموع:** {total_price:,.2f} ليرة
├ 💳 **طريقة الدفع:** {payment_method}
├ 👤 **المشتري:** {buyer_display}
├ 👤 **البائع:** {seller_display}
└ 📅 **تاريخ الطلب:** {created_at[:16]}

💡 **هذا الطلب بانتظار موافقة البائع.**
"""
    
    keyboard = [
        [InlineKeyboardButton("👁️ عرض تفاصيل كاملة", callback_data=f"admin_view_transaction_{transaction_id}")],
        [
            InlineKeyboardButton("⏭️ التالي", callback_data="admin_next_pending_approval"),
            InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
        ]
    ]
    
    await query.edit_message_text(
        transaction_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ إشعارات المسؤول (محدث) ============
async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, message: str, notification_type: str = "info"):
    """إرسال إشعار للمسؤول"""
    try:
        db = DatabaseManager()
        
        pending_offers = len(db.get_pending_offers())
        pending_transactions = len(db.get_pending_transactions())
        pending_approvals = len(db.get_pending_approval_transactions())
        
        notification_text = f"""
🔔 **إشعار جديد للمسؤول**

📋 **تفاصيل الإشعار:**
{message}

📊 **إحصائيات سريعة:**
├ 📝 العروض المنتظرة: {pending_offers}
├ ⏳ طلبات الموافقة: {pending_approvals}
└ 💰 المعاملات المنتظرة: {pending_transactions}

📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        keyboard = []
        
        if pending_offers > 0:
            keyboard.append([InlineKeyboardButton("📝 مراجعة العروض", callback_data="admin_review_offers")])
        
        if pending_approvals > 0:
            keyboard.append([InlineKeyboardButton("⏳ مراجعة الموافقات", callback_data="admin_review_pending_approvals")])
        
        if pending_transactions > 0:
            keyboard.append([InlineKeyboardButton("💰 مراجعة المعاملات", callback_data="admin_review_transactions")])
        
        if keyboard:
            notification_text += "\n👇 **خيارات سريعة:**"
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=notification_text,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode='Markdown'
        )
        
        db.add_notification(
            notification_type=notification_type,
            message=message
        )
        
    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار للمسؤول: {e}")

# ============ معالجة معاملات USDT ============
async def handle_usdt_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال معرف معاملة USDT من المستخدمين"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    if message_text.startswith("0x") and len(message_text) == 66:
        await handle_usdt_transaction_hash(update, context, user_id, message_text)
    else:
        db = DatabaseManager()
        user_transactions_list = db.get_user_transactions(user_id, status='active')
        
        if user_transactions_list:
            await update.message.reply_text(
                "⚠️ **يرجى إدخال معرف معاملة صحيح (Transaction Hash)**\n\n"
                "💡 **مثال:** `0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`\n\n"
                f"🔗 **محفظة البوت:** `{BOT_WALLET_ADDRESS}`\n\n"
                "📋 **كيف أحصل على معرف المعاملة؟**\n"
                "1. بعد إرسال USDT لمحفظة البوت\n"
                "2. اذهب إلى سجل المعاملات في محفظتك\n"
                "3. ابحث عن المعاملة التي أرسلتها\n"
                "4. انسخ الـ Transaction Hash\n"
                "5. ألصقه هنا",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ **لا توجد معاملات نشطة تحتاج لإدخال معرف معاملة**\n\n"
                "💡 **يمكنك:**\n"
                "• تصفح العروض المتاحة\n"
                "• تقديم طلب جديد\n"
                "• انتظار تفعيل معاملتك الحالية",
                parse_mode='Markdown'
            )

# استمرار في القسم التالي...
# استمرار القسم 3 من 3

# ============ استكمال لوحة تحكم المسؤول ============
async def admin_review_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    pending_offers = db.get_pending_offers()
    
    if not pending_offers:
        await query.edit_message_text(
            "📝 **مراجعة العروض المنتظرة**\n\n"
            "✅ **لا توجد عروض منتظرة للمراجعة حالياً**\n\n"
            "🔙 **العودة للوحة التحكم:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    offer = pending_offers[0]
    offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, reputation, completion_rate, total_transactions, user_level = offer
    
    username_display = f"@{username}" if username else "مستخدم"
    payment_methods = payment_method.split(',')
    completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
    
    offer_details = f"""
📝 **عرض #{offer_id} - بانتظار المراجعة**

📋 **تفاصيل العرض:**
├ 📊 **النوع:** {offer_type}
├ 💰 **السعر:** {price:,.2f} ليرة/USDT
├ 📦 **الكمية:** {min_amount} - {max_amount} USDT
├ 💳 **طرق الدفع:** {', '.join(payment_methods[:3])}
├ 👤 **المستخدم:** {username_display}
├ 🏆 **المستوى:** {user_level}
├ ⭐ **السمعة:** {reputation}
├ 📈 **نسبة الإتمام:** {completion_rate_display}% ({total_transactions} صفقات)
└ 📅 **تاريخ الإنشاء:** {created_at[:16]}

⚠️ **اختر الإجراء المناسب:**
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول العرض", callback_data=f"admin_approve_{offer_id}"),
            InlineKeyboardButton("❌ رفض العرض", callback_data=f"admin_reject_{offer_id}")
        ],
        [InlineKeyboardButton("👁️ عرض تفاصيل المستخدم", callback_data=f"admin_view_user_{user_id}")],
        [
            InlineKeyboardButton("⏭️ التالي", callback_data="admin_next_pending"),
            InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
        ]
    ]
    
    context.user_data['pending_offers_index'] = 0
    context.user_data['pending_offers_list'] = pending_offers
    
    await query.edit_message_text(
        offer_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_next_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    if 'pending_offers_index' not in context.user_data or 'pending_offers_list' not in context.user_data:
        await admin_review_offers(update, context)
        return
    
    current_index = context.user_data['pending_offers_index'] + 1
    pending_offers = context.user_data['pending_offers_list']
    
    if current_index >= len(pending_offers):
        current_index = 0
    
    context.user_data['pending_offers_index'] = current_index
    offer = pending_offers[current_index]
    
    offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, reputation, completion_rate, total_transactions, user_level = offer
    
    username_display = f"@{username}" if username else "مستخدم"
    payment_methods = payment_method.split(',')
    completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
    
    offer_details = f"""
📝 **عرض #{offer_id} - بانتظار المراجعة ({current_index + 1}/{len(pending_offers)})**

📋 **تفاصيل العرض:**
├ 📊 **النوع:** {offer_type}
├ 💰 **السعر:** {price:,.2f} ليرة/USDT
├ 📦 **الكمية:** {min_amount} - {max_amount} USDT
├ 💳 **طرق الدفع:** {', '.join(payment_methods[:3])}
├ 👤 **المستخدم:** {username_display}
├ 🏆 **المستوى:** {user_level}
├ ⭐ **السمعة:** {reputation}
├ 📈 **نسبة الإتمام:** {completion_rate_display}% ({total_transactions} صفقات)
└ 📅 **تاريخ الإنشاء:** {created_at[:16]}

⚠️ **اختر الإجراء المناسب:**
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول العرض", callback_data=f"admin_approve_{offer_id}"),
            InlineKeyboardButton("❌ رفض العرض", callback_data=f"admin_reject_{offer_id}")
        ],
        [InlineKeyboardButton("👁️ عرض تفاصيل المستخدم", callback_data=f"admin_view_user_{user_id}")],
        [
            InlineKeyboardButton("⏭️ التالي", callback_data="admin_next_pending"),
            InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
        ]
    ]
    
    await query.edit_message_text(
        offer_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_approve_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    offer_id = int(query.data.split("_")[2])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        await query.answer("❌ العرض غير موجود", show_alert=True)
        return
    
    print(f"🔵 [DEBUG] بدء عملية قبول العرض #{offer_id}...")
    try:
        channel_message_id = await publish_offer_to_channel(update, context, offer_id)
        print(f"🟢 [DEBUG] تم استدعاء دالة النشر للعرض #{offer_id}")
    except Exception as e:
        print(f"🔴 [DEBUG] خطأ في نشر العرض في القناة: {e}")
        logging.error(f"خطأ في نشر العرض في القناة: {e}")
        channel_message_id = 0
    
    db.approve_offer(offer_id, ADMIN_ID, channel_message_id)
    print(f"✅ [DEBUG] تم قبول العرض #{offer_id} في قاعدة البيانات")
    
    user_id = offer[1]
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"""🎉 **تمت الموافقة على عرضك!**

✅ **عرض #{offer_id} تم قبوله وهو الآن نشط**

📊 **تفاصيل العرض المقبول:**
• **النوع:** {offer[2]}
• **السعر:** {offer[5]:,.2f} ليرة/USDT
• **الكمية:** {offer[3]} - {offer[4]} USDT

📢 **تم نشر عرضك في قناة العروض: {CHANNEL_LINK}**

🔍 **يمكن للعملاء الآن رؤية عرضك والاتصال بك**

🏠 **من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
        print(f"📨 [DEBUG] تم إرسال إشعار للمستخدم {user_id}")
    except Exception as e:
        print(f"⚠️ [DEBUG] خطأ في إرسال إشعار للمستخدم: {e}")
        logging.error(f"خطأ في إرسال إشعار للمستخدم: {e}")
    
    await query.answer(f"✅ تم قبول العرض #{offer_id} ونشره في القناة", show_alert=True)
    
    await send_admin_notification(
        context,
        f"✅ تم قبول العرض #{offer_id} من المستخدم {user_id}",
        "offer_approved"
    )
    
    await admin_review_offers(update, context)

async def publish_offer_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    print(f"🔵 [DEBUG] بدء نشر العرض #{offer_id} إلى القناة...")
    db = DatabaseManager()
    offer = db.get_offer_by_id(offer_id)
    
    if not offer:
        print(f"🔴 [DEBUG] فشل النشر: العرض #{offer_id} غير موجود في قاعدة البيانات.")
        return 0
    
    offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, first_name, reputation, completion_rate, total_transactions, completed_transactions, user_level = offer
    
    if price is None:
        print(f"🔴 [DEBUG] السعر None للعرض #{offer_id}")
        return 0
    
    if min_amount is None or max_amount is None:
        print(f"🔴 [DEBUG] الكمية None للعرض #{offer_id}")
        return 0
    
    reputation = reputation if reputation is not None else 100
    completion_rate = completion_rate if completion_rate is not None else 0.0
    total_transactions = total_transactions if total_transactions is not None else 0
    completed_transactions = completed_transactions if completed_transactions is not None else 0
    user_level = user_level if user_level is not None else "جديد"
    transaction_duration = transaction_duration if transaction_duration is not None else 60
    
    username_display = f"@{username}" if username else first_name or f"المستخدم {user_id}"
    
    if offer_type == "بيع":
        offer_emoji = "🔴"
        offer_type_text = "بيع"
    else:
        offer_emoji = "🟢"
        offer_type_text = "شراء"
    
    level_emoji = {
        "ذهبى🥇": "🥇",
        "ذهبى": "🥇",
        "فضي🥈": "🥈",
        "فضي": "🥈",
        "برونزي🥉": "🥉",
        "برونزي": "🥉",
        "ألماسي💎": "💎",
        "جديد": "🆕"
    }.get(user_level, "🆕")
    
    avg_amount = (float(min_amount) + float(max_amount)) / 2
    commission = avg_amount * COMMISSION_RATE
    
    try:
        channel_message = f"""فرصة رقم : {offer_id}
{offer_emoji} التاجر يريد {offer_type_text} "USDT"
__
💰 الكمية : من {min_amount} إلى {max_amount}
📊 سعر الصرف : {float(price):,.2f}
🏦 طرق الدفع : {payment_method}
⏳ مدة المعاملة : {transaction_duration} دقيقة
__
معلومات عن التاجر :
👤 المستوى : {user_level}{level_emoji}
📈 نسبة الإتمام: {float(completion_rate):.1f}%  ({total_transactions} صفقات)
🧐 السمعة : ⭐️ {float(reputation):.1f}
📉️ عمولة الوسيط: ({float(commission):.2f}$/{float(avg_amount):.0f}$)
"""
    except Exception as format_error:
        print(f"🔴 [DEBUG] خطأ في تنسيق الرسالة: {format_error}")
        channel_message = f"""فرصة رقم : {offer_id}
{offer_emoji} التاجر يريد {offer_type_text} "USDT"
__
💰 الكمية : من {min_amount} إلى {max_amount}
📊 سعر الصرف : {price}
🏦 طرق الدفع : {payment_method}
⏳ مدة المعاملة : {transaction_duration} دقيقة
__
معلومات عن التاجر :
👤 المستوى : {user_level}{level_emoji}
📈 نسبة الإتمام: {completion_rate}%  ({total_transactions} صفقات)
🧐 السمعة : ⭐️ {reputation}
📉️ عمولة الوسيط: ({commission}$/{avg_amount}$)
"""
    
    keyboard = []
    
    if offer_type == "بيع":
        keyboard.append([InlineKeyboardButton("🛒 شراء هذا العرض", url=f"https://t.me/Qcss_bot?start=offer_{offer_id}")])
        keyboard.append([InlineKeyboardButton("🔍 تصفح العروض الأخرى", url=f"https://t.me/Qcss_bot?start=browse")])
    else:
        keyboard.append([InlineKeyboardButton("💰 البيع لهذا الزبون", url=f"https://t.me/Qcss_bot?start=offer_{offer_id}")])
        keyboard.append([InlineKeyboardButton("🔍 تصفح العروض الأخرى", url=f"https://t.me/Qcss_bot?start=browse")])
    
    try:
        print(f"🟡 [DEBUG] محاولة إرسال رسالة العرض #{offer_id} إلى القناة: {CHANNEL_ID}")
        
        try:
            chat = await context.bot.get_chat(CHANNEL_ID)
            print(f"✅ [DEBUG] يمكن الوصول للقناة: {chat.title}")
        except Exception as chat_error:
            print(f"🔴 [DEBUG] لا يمكن الوصول للقناة: {chat_error}")
            return 0
        
        message = await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=channel_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        print(f"✅ [DEBUG] تم النشر بنجاح! معرف الرسالة في القناة: {message.message_id}")
        return message.message_id
        
    except Exception as e:
        print(f"🔴 [DEBUG] فشل إرسال الرسالة إلى القناة. الخطأ: {e}")
        print(f"🔴 [DEBUG] تفاصيل العرض:")
        print(f"  - offer_id: {offer_id}")
        print(f"  - price: {price} (type: {type(price)})")
        print(f"  - reputation: {reputation} (type: {type(reputation)})")
        print(f"  - completion_rate: {completion_rate} (type: {type(completion_rate)})")
        print(f"  - channel_message length: {len(channel_message)}")
        
        logging.error(f"خطأ في نشر العرض في القناة: {e}")
        return 0

async def admin_reject_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    offer_id = int(query.data.split("_")[2])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    context.user_data['rejecting_offer_id'] = offer_id
    context.user_data['awaiting_reject_reason'] = True
    
    await query.edit_message_text(
        "❌ **رفض العرض**\n\n"
        "📝 **يرجى إدخال سبب الرفض:**\n"
        "(مثال: السعر غير مناسب، طرق دفع غير مقبولة، إلخ)",
        parse_mode='Markdown'
    )

async def admin_review_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    pending_transactions = db.get_pending_transactions()
    
    if not pending_transactions:
        await query.edit_message_text(
            "💰 **مراجعة المعاملات المنتظرة**\n\n"
            "✅ **لا توجد معاملات منتظرة للمراجعة حالياً**\n\n"
            "🔙 **العودة للوحة التحكم:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    transaction = pending_transactions[0]
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, seller_username, offer_type = transaction
    
    buyer_display = f"@{buyer_username}" if buyer_username else f"المشتري {buyer_id}"
    seller_display = f"@{seller_username}" if seller_username else f"البائع {seller_id}"
    
    transaction_details = f"""
💰 **معاملة #{transaction_id} - بانتظار المراجعة**

📋 **تفاصيل المعاملة:**
├ 📊 **النوع:** {offer_type}
├ 💰 **الكمية:** {amount} USDT
├ 📈 **السعر:** {price:,.2f} ليرة/USDT
├ 💵 **المجموع:** {total_price:,.2f} ليرة
├ 💳 **طريقة الدفع:** {payment_method}
├ 👤 **المشتري:** {buyer_display}
├ 👤 **البائع:** {seller_display}
└ 📅 **تاريخ الطلب:** {created_at[:16]}

⚠️ **اختر الإجراء المناسب:**
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول المعاملة", callback_data=f"admin_approve_transaction_{transaction_id}"),
            InlineKeyboardButton("❌ رفض المعاملة", callback_data=f"admin_reject_transaction_{transaction_id}")
        ],
        [InlineKeyboardButton("👁️ عرض تفاصيل كاملة", callback_data=f"admin_view_transaction_{transaction_id}")],
        [
            InlineKeyboardButton("⏭️ التالي", callback_data="admin_next_transaction"),
            InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
        ]
    ]
    
    context.user_data['pending_transactions_index'] = 0
    context.user_data['pending_transactions_list'] = pending_transactions
    
    await query.edit_message_text(
        transaction_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_next_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    if 'pending_transactions_index' not in context.user_data or 'pending_transactions_list' not in context.user_data:
        await admin_review_transactions(update, context)
        return
    
    current_index = context.user_data['pending_transactions_index'] + 1
    pending_transactions = context.user_data['pending_transactions_list']
    
    if current_index >= len(pending_transactions):
        current_index = 0
    
    context.user_data['pending_transactions_index'] = current_index
    transaction = pending_transactions[current_index]
    
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, seller_username, offer_type = transaction
    
    buyer_display = f"@{buyer_username}" if buyer_username else f"المشتري {buyer_id}"
    seller_display = f"@{seller_username}" if seller_username else f"البائع {seller_id}"
    
    transaction_details = f"""
💰 **معاملة #{transaction_id} - بانتظار المراجعة ({current_index + 1}/{len(pending_transactions)})**

📋 **تفاصيل المعاملة:**
├ 📊 **النوع:** {offer_type}
├ 💰 **الكمية:** {amount} USDT
├ 📈 **السعر:** {price:,.2f} ليرة/USDT
├ 💵 **المجموع:** {total_price:,.2f} ليرة
├ 💳 **طريقة الدفع:** {payment_method}
├ 👤 **المشتري:** {buyer_display}
├ 👤 **البائع:** {seller_display}
└ 📅 **تاريخ الطلب:** {created_at[:16]}

⚠️ **اختر الإجراء المناسب:**
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول المعاملة", callback_data=f"admin_approve_transaction_{transaction_id}"),
            InlineKeyboardButton("❌ رفض المعاملة", callback_data=f"admin_reject_transaction_{transaction_id}")
        ],
        [InlineKeyboardButton("👁️ عرض تفاصيل كاملة", callback_data=f"admin_view_transaction_{transaction_id}")],
        [
            InlineKeyboardButton("⏭️ التالي", callback_data="admin_next_transaction"),
            InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
        ]
    ]
    
    await query.edit_message_text(
        transaction_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_view_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    transaction_id = int(query.data.split("_")[3])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    transaction = db.get_transaction_by_id(transaction_id)
    
    if not transaction:
        await query.answer("❌ المعاملة غير موجودة", show_alert=True)
        return
    
    transaction_details = transaction
    
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, buyer_name, seller_username, seller_name, offer_type, offer_payment_methods = transaction_details
    
    buyer_display = f"@{buyer_username}" if buyer_username else buyer_name or f"المشتري {buyer_id}"
    seller_display = f"@{seller_username}" if seller_username else seller_name or f"البائع {seller_id}"
    
    details_text = f"""
🔍 **تفاصيل كاملة للمعاملة #{transaction_id}**

📋 **معلومات المعاملة:**
┌ 📊 **النوع:** {offer_type}
├ 💰 **الكمية:** {amount} USDT
├ 📈 **السعر:** {price:,.2f} ليرة/USDT
├ 💵 **المجموع:** {total_price:,.2f} ليرة
├ 💳 **طريقة الدفع المختارة:** {payment_method}
├ 📋 **طرق الدفع المتاحة:** {offer_payment_methods}
├ ⏳ **الحالة:** {status}
└ 📅 **تاريخ الطلب:** {created_at[:16]}

👥 **أطراف المعاملة:**
┌ 👤 **المشتري:** {buyer_display} (ID: {buyer_id})
├ 🔄 **تأكيد المشتري:** {'✅' if buyer_confirmed == 1 else '❌'}
├ 👤 **البائع:** {seller_display} (ID: {seller_id})
└ 🔄 **تأكيد البائع:** {'✅' if seller_confirmed == 1 else '❌'}

📊 **معلومات العرض الأصلية:**
• **رقم العرض:** #{offer_id}
• **نوع العرض:** {offer_type}

📝 **معلومات المراجعة:**
• **تمت المراجعة:** {'✅' if admin_approved == 1 else '❌'}
• **معرف المسؤول:** {admin_id or 'لم تتم'}
• **تاريخ المراجعة:** {admin_approval_date[:16] if admin_approval_date else 'لم تتم'}
• **سبب الإلغاء:** {cancellation_reason or 'لا يوجد'}
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول المعاملة", callback_data=f"admin_approve_transaction_{transaction_id}"),
            InlineKeyboardButton("❌ رفض المعاملة", callback_data=f"admin_reject_transaction_{transaction_id}")
        ],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="admin_review_transactions")]
    ]
    
    await query.edit_message_text(
        details_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_approve_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    
    user_id = query.from_user.id if query else update.effective_user.id
    
    if user_id != ADMIN_ID:
        if query:
            await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    if query:
        await query.answer()
    
    db = DatabaseManager()
    db.approve_transaction(transaction_id, ADMIN_ID)
    
    transaction = db.get_transaction_by_id(transaction_id)
    if transaction:
        transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, buyer_name, seller_username, seller_name, offer_type, offer_payment_methods = transaction
        
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=f"""✅ **تمت الموافقة على معاملتك!**

🎉 **معاملة #{transaction_id} تمت الموافقة عليها من قبل الإدارة**

📋 **تفاصيل المعاملة المقبولة:**
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {payment_method}
• **رقم العرض:** #{offer_id}

🔔 **يمكنك الآن التواصل مع البائع لإتمام الصفقة**

🏠 **من الواجهة الرئيسية:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال إشعار للمشتري: {e}")
        
        try:
            await context.bot.send_message(
                chat_id=seller_id,
                text=f"""✅ **تمت الموافقة على معاملة تشمل عرضك!**

🎉 **معاملة #{transaction_id} تمت الموافقة عليها من قبل الإدارة**

📋 **تفاصيل المعاملة المقبولة:**
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {payment_method}
• **رقم العرض:** #{offer_id}

👤 **المشتري:** {buyer_name or buyer_username or f"المستخدم {buyer_id}"}

🔔 **يمكنك الآن التواصل مع المشتري لإتمام الصفقة**

🏠 **من الواجهة الرئيسية:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال إشعار للبائع: {e}")
    
    if query:
        await query.answer(f"✅ تم قبول المعاملة #{transaction_id}", show_alert=True)
        
        await send_admin_notification(
            context,
            f"✅ تمت الموافقة على المعاملة #{transaction_id}",
            "transaction_approved"
        )
        
        await admin_review_transactions(update, context)

async def admin_reject_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    context.user_data['rejecting_transaction_id'] = transaction_id
    context.user_data['awaiting_transaction_reject_reason'] = True
    
    await query.edit_message_text(
        "❌ **رفض المعاملة**\n\n"
        "📝 **يرجى إدخال سبب الرفض:**\n"
        "(مثال: معلومات غير صحيحة، مخالفة للشروط، إلخ)",
        parse_mode='Markdown'
    )

async def admin_manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    users = db.get_all_users()
    
    if not users:
        await query.edit_message_text(
            "👥 **إدارة المستخدمين**\n\n"
            "📭 **لا يوجد مستخدمين مسجلين حالياً**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    users_text = "👥 **قائمة المستخدمين**\n\n"
    
    for idx, user in enumerate(users[:10], 1):
        user_id, username, first_name, phone_number, join_date, reputation, is_banned, total_transactions, completed_transactions, user_level, accepted_terms, joined_channel, registration_step = user[:13]
        username_display = f"@{username}" if username else first_name or f"المستخدم {user_id}"
        ban_status = "🚫 محظور" if is_banned == 1 else "✅ نشط"
        
        registration_status = ""
        if registration_step == 'completed':
            registration_status = "✅ مسجل"
        elif registration_step == 'contact_registration':
            registration_status = "📱 يحتاج جهة اتصال"
        elif registration_step == 'channel_check':
            registration_status = "🔗 يحتاج قناة"
        elif registration_step == 'terms':
            registration_status = "📜 يحتاج شروط"
        else:
            registration_status = "⚪ غير مكتمل"
        
        users_text += f"{idx}. **{username_display}** (ID: `{user_id}`)\n"
        users_text += f"   📞 {phone_number or 'لا يوجد'} | {registration_status} | {ban_status} | {join_date[:10]}\n\n"
    
    keyboard = []
    
    for user in users[:5]:
        user_id = user[0]
        username_display = f"@{user[1]}" if user[1] else user[2] or f"المستخدم {user_id}"
        keyboard.append([InlineKeyboardButton(f"👤 إدارة {username_display}", callback_data=f"admin_manage_user_{user_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="admin_search_user")],
        [InlineKeyboardButton("📊 إحصائيات التسجيل", callback_data="admin_registration_stats")],
        [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
    ])
    
    await query.edit_message_text(
        users_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_manage_specific_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = int(query.data.split("_")[3])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    user_info = db.get_user_info(user_id)
    
    if not user_info:
        await query.edit_message_text(
            "❌ **المستخدم غير موجود**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة لإدارة المستخدمين", callback_data="admin_manage_users")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    user_id, username, first_name, phone_number, contact_info, join_date, reputation, is_banned, ban_reason, total_transactions, completed_transactions, completion_rate, user_level, accepted_terms, joined_channel, registration_step = user_info
    
    username_display = f"@{username}" if username else first_name or f"المستخدم {user_id}"
    ban_status = "🚫 محظور" if is_banned == 1 else "✅ نشط"
    
    registration_status = ""
    if registration_step == 'completed':
        registration_status = "✅ مسجل بالكامل"
    elif registration_step == 'contact_registration':
        registration_status = "⏳ بانتظار جهة اتصال"
    elif registration_step == 'channel_check':
        registration_status = "⏳ يحتاج الانضمام للقناة"
    elif registration_step == 'terms':
        registration_status = "⏳ يحتاج قبول الشروط"
    else:
        registration_status = "⚪ غير مكتمل"
    
    user_offers = db.get_user_offers(user_id)
    active_offers = sum(1 for offer in user_offers if offer[7] == 'active')
    pending_offers = sum(1 for offer in user_offers if offer[7] == 'pending')
    
    user_transactions_list = db.get_user_transactions(user_id)
    active_transactions = sum(1 for t in user_transactions_list if t[8] == 'active')
    pending_transactions = sum(1 for t in user_transactions_list if t[8] == 'pending_admin')
    
    completion_rate_display = "0.0" if completion_rate is None else f"{completion_rate:.1f}"
    
    user_details = f"""
👤 **إدارة المستخدم: {username_display}**

📋 **المعلومات الشخصية:**
├ 🆔 **رقم المعرف:** `{user_id}`
├ 📅 **تاريخ الانضمام:** {join_date[:10]}
├ 📞 **رقم الهاتف:** {phone_number or 'غير مسجل'}
├ 📱 **معلومات الاتصال:** {contact_info or 'غير مسجل'}
├ 🏆 **المستوى:** {user_level}
├ ⭐ **السمعة:** {reputation}
├ 📊 **حالة التسجيل:** {registration_status}
├ ✅ **قبل الشروط:** {'نعم' if accepted_terms == 1 else 'لا'}
├ 🔗 **انضم للقناة:** {'نعم' if joined_channel == 1 else 'لا'}
├ 📈 **الحالة:** {ban_status}
└ 📝 **سبب الحظر:** {ban_reason or "لا يوجد"}

📊 **الإحصائيات:**
├ 📈 **إجمالي الصفقات:** {total_transactions}
├ ✅ **الصفقات المكتملة:** {completed_transactions}
└ 📊 **نسبة الإتمام:** {completion_rate_display}%

📊 **إحصائيات العروض:**
├ ✅ **النشطة:** {active_offers}
├ ⏳ **بانتظار المراجعة:** {pending_offers}
└ 📋 **الإجمالي:** {len(user_offers)}

💰 **إحصائيات المعاملات:**
├ ⏳ **بانتظار المراجعة:** {pending_transactions}
├ ✅ **النشطة:** {active_transactions}
└ 📋 **الإجمالي:** {len(user_transactions_list)}

🔧 **خيارات الإدارة:**
    """
    
    keyboard = []
    
    if is_banned == 1:
        keyboard.append([InlineKeyboardButton("🔓 رفع الحظر عن المستخدم", callback_data=f"admin_unban_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🚫 حظر المستخدم", callback_data=f"admin_ban_{user_id}")])
    
    if not db.is_user_registered(user_id):
        keyboard.append([InlineKeyboardButton("✅ إكمال التسجيل يدوياً", callback_data=f"admin_complete_registration_{user_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("📨 إرسال رسالة للمستخدم", callback_data=f"admin_message_{user_id}")],
        [InlineKeyboardButton("📋 عرض عروض المستخدم", callback_data=f"admin_user_offers_{user_id}")],
        [
            InlineKeyboardButton("🔙 العودة للقائمة", callback_data="admin_manage_users"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="admin_panel")
        ]
    ])
    
    await query.edit_message_text(
        user_details,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = int(query.data.split("_")[2])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    context.user_data['banning_user_id'] = user_id
    context.user_data['awaiting_ban_reason'] = True
    
    await query.edit_message_text(
        "🚫 **حظر المستخدم**\n\n"
        "📝 **يرجى إدخال سبب الحظر:**\n"
        "(مثال: مخالفة الشروط، نشر عروض وهمية، إلخ)",
        parse_mode='Markdown'
    )

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = int(query.data.split("_")[2])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    db = DatabaseManager()
    db.unban_user(user_id)
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="""✅ **تم رفع الحظر عن حسابك**

🔓 **يمكنك الآن استخدام جميع خدمات البوت مرة أخرى**

🏠 **من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار للمستخدم: {e}")
    
    await query.answer("✅ تم رفع الحظر عن المستخدم", show_alert=True)
    await admin_manage_specific_user(update, context)

async def admin_message_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = int(query.data.split("_")[2])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    context.user_data['messaging_user_id'] = user_id
    context.user_data['awaiting_admin_message'] = True
    
    await query.edit_message_text(
        "📨 **إرسال رسالة للمستخدم**\n\n"
        "✏️ **يرجى كتابة الرسالة التي تريد إرسالها:**",
        parse_mode='Markdown'
    )

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    context.user_data['awaiting_broadcast_message'] = True
    
    await query.edit_message_text(
        "📢 **بث رسالة عامة**\n\n"
        "✏️ **يرجى كتابة الرسالة التي تريد بثها لجميع المستخدمين:**\n\n"
        "⚠️ **ملاحظة:** سيتم إرسال هذه الرسالة لجميع المستخدمين النشطين.",
        parse_mode='Markdown'
    )

async def admin_active_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    active_offers = db.get_active_offers()
    
    if not active_offers:
        await query.edit_message_text(
            "✅ **العروض النشطة**\n\n"
            "📭 **لا توجد عروض نشطة حالياً**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    offers_text = "✅ **العروض النشطة**\n\n"
    
    for idx, offer in enumerate(active_offers[:10], 1):
        offer_id, user_id, offer_type, min_amount, max_amount, price, payment_method, status, admin_reviewed, admin_id, review_date, created_at, channel_message_id, transaction_duration, username, reputation, completion_rate, total_transactions, user_level = offer
        
        username_display = f"@{username}" if username else "مستخدم"
        offer_type_arabic = "بيع" if offer_type == "بيع" else "شراء"
        
        offers_text += f"""**{idx}. عرض #{offer_id}** ({offer_type_arabic})
💰 **السعر:** {price:,.2f} ليرة/USDT
📦 **الكمية:** {min_amount}-{max_amount} USDT
👤 **المستخدم:** {username_display} 🏆{user_level}
📅 **النشر:** {created_at[:16]}

"""
    
    keyboard = [
        [InlineKeyboardButton("🔍 بحث عن عرض", callback_data="admin_search_offer")],
        [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        offers_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    
    pending_offers = db.get_pending_offers()
    active_offers = db.get_active_offers()
    pending_transactions = db.get_pending_transactions()
    pending_approvals = db.get_pending_approval_transactions()
    all_users = db.get_all_users()
    banned_users = [user for user in all_users if user[5] == 1]
    
    buy_offers = [offer for offer in active_offers if offer[2] == "شراء"]
    sell_offers = [offer for offer in active_offers if offer[2] == "بيع"]
    
    week_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
    new_users = []
    for user in all_users:
        join_date = datetime.strptime(user[4], '%Y-%m-%d %H:%M:%S')
        if join_date.timestamp() > week_ago:
            new_users.append(user)
    
    levels = {"ذهبى🥇": 0, "فضي🥈": 0, "برونزي🥉": 0, "جديد": 0, "ألماسي💎": 0}
    for user in all_users:
        user_level = user[9] if len(user) > 9 else "جديد"
        if user_level in levels:
            levels[user_level] += 1
    
    registered_count = sum(1 for user in all_users if db.is_user_registered(user[0]))
    in_registration = len(all_users) - registered_count - len(banned_users)
    active_transactions = len([t for t in db.get_pending_transactions() if t[8] == 'active'])
    
    total_revenue = 0
    completed_transactions = db.get_user_transactions(ADMIN_ID, status='completed')
    for transaction in completed_transactions:
        if len(transaction) > 15:
            total_revenue += transaction[15] or 0
    
    stats_text = f"""
📊 **الإحصائيات الكاملة**

👥 **المستخدمين:**
├ 📈 **إجمالي المستخدمين:** {len(all_users)}
├ ✅ **مسجلين بالكامل:** {registered_count}
├ ⏳ **قيد التسجيل:** {in_registration}
├ 🆕 **مستخدمين جدد (أسبوع):** {len(new_users)}
├ ✅ **نشطين:** {len(all_users) - len(banned_users)}
├ 🚫 **محظورين:** {len(banned_users)}
├ 💎 **ألماسي:** {levels['ألماسي💎']}
├ 🥇 **ذهبى:** {levels['ذهبى🥇']}
├ 🥈 **فضي:** {levels['فضي🥈']}
├ 🥉 **برونزي:** {levels['برونزي🥉']}
└ 🆕 **جدد:** {levels['جديد']}

📋 **العروض:**
├ ⏳ **بانتظار المراجعة:** {len(pending_offers)}
├ ✅ **نشطة:** {len(active_offers)}
├ 💰 **عروض شراء:** {len(buy_offers)}
└ 💎 **عروض بيع:** {len(sell_offers)}

💰 **المعاملات:**
├ ⏳ **بانتظار المراجعة:** {len(pending_transactions)}
├ ⏳ **طلبات موافقة:** {len(pending_approvals)}
├ ✅ **نشطة:** {active_transactions}
└ 📈 **إجمالي المعاملات:** {len(pending_transactions) + active_transactions + len(pending_approvals)}

💰 **معلومات مالية:**
├ 💳 **دفعوا رسوم الدخول:** {sum(1 for user in all_users if db.has_paid_entry_fee(user[0]))}
├ 💰 **إجمالي الإيرادات:** {total_revenue:.2f}$
└ ⭐ **متوسط السمعة:** {sum(user[5] for user in all_users) / len(all_users) if all_users else 0:.1f}

📅 **آخر تحديث:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    keyboard = [
        [InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data="admin_statistics")],
        [InlineKeyboardButton("📈 رسوم بيانية", callback_data="admin_charts")],
        [InlineKeyboardButton("📊 إحصائيات التسجيل", callback_data="admin_registration_stats")],
        [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_registration_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    await query.answer()
    
    db = DatabaseManager()
    all_users = db.get_all_users()
    
    steps_count = {
        'completed': 0,
        'contact_registration': 0,
        'channel_check': 0,
        'terms': 0,
        'start': 0,
        'other': 0
    }
    
    for user in all_users:
        step = user[12] if len(user) > 12 else 'other'
        if step in steps_count:
            steps_count[step] += 1
        else:
            steps_count['other'] += 1
    
    registered = sum(1 for user in all_users if db.is_user_registered(user[0]))
    
    stats_text = f"""
📊 **إحصائيات التسجيل**

👥 **توزيع المستخدمين حسب خطوة التسجيل:**
├ ✅ **مسجلين بالكامل:** {steps_count['completed']} ({registered} فعلياً)
├ 📱 **بانتظار جهة اتصال:** {steps_count['contact_registration']}
├ 🔗 **بانتظار الانضمام للقناة:** {steps_count['channel_check']}
├ 📜 **بانتظار قبول الشروط:** {steps_count['terms']}
├ 🏁 **في البداية:** {steps_count['start']}
└ ❓ **حالات أخرى:** {steps_count['other']}

📈 **النسب المئوية:**
├ ✅ **نسبة الإكمال:** {(steps_count['completed'] / len(all_users) * 100) if all_users else 0:.1f}%
├ 📱 **نسبة بانتظار جهة اتصال:** {(steps_count['contact_registration'] / len(all_users) * 100) if all_users else 0:.1f}%
├ 🔗 **نسبة بانتظار قناة:** {(steps_count['channel_check'] / len(all_users) * 100) if all_users else 0:.1f}%
└ 📜 **نسبة بانتظار شروط:** {(steps_count['terms'] / len(all_users) * 100) if all_users else 0:.1f}%

💡 **تحليل:**
• **معدل إكمال التسجيل:** {((steps_count['completed'] + steps_count['contact_registration']) / len(all_users) * 100) if all_users else 0:.1f}% (بعد الشروط والقناة)
• **أكبر نقطة تسرب:** {max(steps_count, key=steps_count.get)} بتسريب {steps_count[max(steps_count, key=steps_count.get)]} مستخدم

📅 **آخر تحديث:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    keyboard = [
        [InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data="admin_registration_stats")],
        [InlineKeyboardButton("📊 الإحصائيات الكاملة", callback_data="admin_statistics")],
        [InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_complete_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = int(query.data.split("_")[3])
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ ليس لديك صلاحية الوصول", show_alert=True)
        return
    
    db = DatabaseManager()
    db.save_user_contact_info(user_id, "تم التسجيل يدوياً", f"تم إكمال التسجيل بواسطة المسؤول {ADMIN_ID}")
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="""🎉 **تم إكمال تسجيل حسابك!**

✅ **تم إكمال عملية التسجيل بنجاح من قبل الإدارة.**

🔓 **يمكنك الآن استخدام جميع خدمات البوت بشكل كامل.**

✨ **مميزات حسابك الجديد:**
• إنشاء عروض بيع وشراء
• تصفح جميع العروض المتاحة
• إدارة ملفك الشخصي
• والكثير من الميزات الأخرى

🏠 **ابدأ الآن من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار للمستخدم: {e}")
    
    await query.answer("✅ تم إكمال تسجيل المستخدم يدوياً", show_alert=True)
    await admin_manage_specific_user(update, context)

# ============ معالجة إدخال معرف معاملة USDT ============
async def handle_usdt_hash_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    if message_text.startswith("0x") and len(message_text) == 66:
        await handle_usdt_transaction_hash(update, context, user_id, message_text)
    else:
        db = DatabaseManager()
        user_transactions_list = db.get_user_transactions(user_id, status='active')
        
        if user_transactions_list:
            await update.message.reply_text(
                "⚠️ **يرجى إدخال معرف معاملة صحيح (Transaction Hash)**\n\n"
                "💡 **مثال:** `0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`\n\n"
                f"🔗 **محفظة البوت:** `{BOT_WALLET_ADDRESS}`\n\n"
                "📋 **كيف أحصل على معرف المعاملة؟**\n"
                "1. بعد إرسال USDT لمحفظة البوت\n"
                "2. اذهب إلى سجل المعاملات في محفظتك\n"
                "3. ابحث عن المعاملة التي أرسلتها\n"
                "4. انسخ الـ Transaction Hash\n"
                "5. ألصقه هنا",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ **لا توجد معاملات نشطة تحتاج لإدخال معرف معاملة**\n\n"
                "💡 **يمكنك:**\n"
                "• تصفح العروض المتاحة\n"
                "• تقديم طلب جديد\n"
                "• انتظار تفعيل معاملتك الحالية",
                parse_mode='Markdown'
            )

# ============ معالجة المدفوعات وتأكيدها ============
async def handle_payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id: int):
    """معالجة تأكيد وصول المبلغ من البائع للمشتري"""
    db = DatabaseManager()
    transaction = db.get_transaction_by_id(transaction_id)
    
    if not transaction:
        return
    
    transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, buyer_name, seller_username, seller_name, offer_type, offer_payment_methods = transaction
    
    if status != 'active':
        return
    
    # إرسال إشعار للبائع لتأكيد إرسال المبلغ
    try:
        await context.bot.send_message(
            chat_id=seller_id,
            text=f"""✅ **تم تأكيد استلام USDT من المشتري**

🎉 **تم التحقق من وصول {amount} USDT لمحفظة البوت**

📋 **تفاصيل المعاملة:**
• **رقم المعاملة:** #{transaction_id}
• **الكمية:** {amount} USDT
• **المبلغ المستحق:** {total_price:,.2f} ليرة
• **طريقة الدفع:** {payment_method}

👤 **المشتري:** {buyer_name or buyer_username or f"المستخدم {buyer_id}"}

💡 **الآن يمكنك إرسال المبلغ للمشتري عبر:**
`{payment_method}`

⚠️ **بعد إرسال المبلغ، أرسل إثبات الدفع (صورة التحويل).**

🏠 **من الواجهة الرئيسية:**""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
            ]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار للبائع: {e}")

# ============ معالجة إثباتات الدفع ============
async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, photo_id: str):
    """معالجة إرسال إثبات الدفع من البائع"""
    try:
        db = DatabaseManager()
        user_transactions_list = db.get_user_transactions(user_id, status='active')
        
        if not user_transactions_list:
            await update.message.reply_text(
                "❌ **لا توجد معاملات نشطة تحتاج لإثبات دفع**",
                parse_mode='Markdown'
            )
            return
        
        latest_transaction = user_transactions_list[0]
        transaction_id = latest_transaction[0]
        
        db.update_transaction_payment_proof(transaction_id, photo_id)
        
        transaction = db.get_transaction_by_id(transaction_id)
        if transaction:
            transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, buyer_name, seller_username, seller_name, offer_type, offer_payment_methods = transaction
            
            await update.message.reply_text(
                f"""✅ **تم استلام إثبات الدفع بنجاح!**

📸 **تم حفظ صورة إثبات الدفع للمعاملة #{transaction_id}**

📋 **سيتم مراجعة الإثبات من قبل الإدارة.**

⏳ **قد تستغرق عملية المراجعة بعض الوقت.**

🏠 **من الواجهة الرئيسية:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
            
            await send_admin_notification(
                context,
                f"📸 تم إرسال إثبات دفع للمعاملة #{transaction_id} من البائع {user_id}",
                "payment_proof"
            )
            
            try:
                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=photo_id,
                    caption=f"""📸 **إثبات دفع جديد**

💰 **المعاملة:** #{transaction_id}
👤 **البائع:** {seller_name or seller_username or f"المستخدم {seller_id}"}
👤 **المشتري:** {buyer_name or buyer_username or f"المستخدم {buyer_id}"}
💵 **المبلغ:** {total_price:,.2f} ليرة
💳 **طريقة الدفع:** {payment_method}

⚠️ **يرجى مراجعة إثبات الدفع والتحقق منه.**""",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"خطأ في إرسال إشعار للمسؤول: {e}")
        
    except Exception as e:
        logging.error(f"خطأ في حفظ إثبات الدفع: {e}")
        await update.message.reply_text(
            "❌ **حدث خطأ في حفظ إثبات الدفع. يرجى المحاولة لاحقاً.**",
            parse_mode='Markdown'
        )

# ============ إكمال المعاملة وإرسال USDT ============
async def complete_transaction_and_send_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id: int, usdt_hash: str):
    """إكمال المعاملة وإرسال USDT للمشتري"""
    db = DatabaseManager()
    
    db.complete_transaction(transaction_id, usdt_hash)
    
    transaction = db.get_transaction_by_id(transaction_id)
    if transaction:
        transaction_id, offer_id, buyer_id, seller_id, amount, price, total_price, payment_method, status, admin_approved, admin_id, admin_approval_date, created_at, completed_at, buyer_confirmed, seller_confirmed, cancellation_reason, buyer_username, buyer_name, seller_username, seller_name, offer_type, offer_payment_methods = transaction
        
        commission = transaction[15] if len(transaction) > 15 else 0
        
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=f"""🎉 **تم إكمال المعاملة بنجاح!**

✅ **تم إرسال {amount} USDT لمحفظتك**

📋 **تفاصيل المعاملة المكتملة:**
• **رقم المعاملة:** #{transaction_id}
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **عمولة الوسيط:** {commission:.2f}$
• **Transaction Hash:** `{usdt_hash[:20]}...`

💰 **يمكنك الآن التحقق من وصول USDT لمحفظتك.**

⭐ **شكراً لاستخدامك QuickCashSY!**

🏠 **من الواجهة الرئيسية:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال إشعار للمشتري: {e}")
        
        try:
            await context.bot.send_message(
                chat_id=seller_id,
                text=f"""🎉 **تم إكمال المعاملة بنجاح!**

✅ **تم إرسال {amount} USDT للمشتري بنجاح**

📋 **تفاصيل المعاملة المكتملة:**
• **رقم المعاملة:** #{transaction_id}
• **الكمية:** {amount} USDT
• **السعر:** {price:,.2f} ليرة/USDT
• **المجموع:** {total_price:,.2f} ليرة
• **عمولة الوسيط:** {commission:.2f}$

💰 **تم خصم عمولة الوسيط من المبلغ المستحق.**

⭐ **شكراً لاستخدامك QuickCashSY!**

🏠 **من الواجهة الرئيسية:**""",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 الواجهة الرئيسية", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"خطأ في إرسال إشعار للبائع: {e}")
        
        await send_admin_notification(
            context,
            f"✅ تم إكمال المعاملة #{transaction_id} وإرسال {amount} USDT للمشتري",
            "transaction_completed"
        )

# ============ معالجة رسائل الصور (إثباتات الدفع) ============
async def handle_photo_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة رسائل الصور (إثباتات الدفع)"""
    user_id = update.effective_user.id
    photo = update.message.photo[-1] if update.message.photo else None
    
    if not photo:
        return
    
    db = DatabaseManager()
    
    user_transactions_list = db.get_user_transactions(user_id, status='active')
    if user_transactions_list:
        # البائع يرسل إثبات دفع
        await handle_payment_proof(update, context, user_id, photo.file_id)
    else:
        user_transactions_list = db.get_user_transactions(user_id, status='pending_approval')
        if user_transactions_list:
            # المشتري يرسل إثبات إرسال USDT
            latest_transaction = user_transactions_list[0]
            transaction_id = latest_transaction[0]
            
            db.update_transaction_payment_proof(transaction_id, photo.file_id)
            
            await update.message.reply_text(
                "✅ **تم استلام صورة إثبات إرسال USDT بنجاح!**\n\n"
                "📋 **سيتم مراجعة الصورة من قبل الإدارة.**\n"
                "⏳ **قد تستغرق عملية المراجعة بعض الوقت.**",
                parse_mode='Markdown'
            )
            
            await send_admin_notification(
                context,
                f"📸 تم إرسال إثبات إرسال USDT للمعاملة #{transaction_id} من المشتري {user_id}",
                "usdt_proof"
            )

# ============ معالجة رسائل النص العامة ============
async def handle_general_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة رسائل النص العامة"""
    user_id = update.effective_user.id
    message_text = update.message.text if update.message.text else ""
    
    db = DatabaseManager()
    is_banned, ban_reason = db.is_user_banned(user_id)
    
    if is_banned and user_id != ADMIN_ID:
        await update.message.reply_text(
            f"🚫 **تم حظر حسابك**\n\n"
            f"**السبب:** {ban_reason}\n\n"
            f"للاستفسار، تواصل مع الدعم: {SUPPORT_USERNAME}",
            parse_mode='Markdown'
        )
        return
    
    # التحقق إذا كان النص معرف معاملة USDT
    if message_text.startswith("0x") and len(message_text) == 66:
        await handle_usdt_hash_input(update, context)
        return
    
    # التحقق إذا كان النص رسالة للمسؤول
    if user_id == ADMIN_ID and 'awaiting_' in str(context.user_data):
        await handle_admin_messages(update, context, message_text)
        return
    
    # التحقق إذا كان المستخدم في حالة تعديل عرض
    if user_id in editing_offers:
        await handle_offer_editing(update, context, message_text)
        return
    
    # التحقق إذا كان المستخدم في حالة إنشاء عرض
    if user_id in user_states:
        await handle_offer_creation(update, context, message_text)
        return
    
    # التحقق إذا كان المستخدم في حالة معاملة
    if user_id in user_transactions:
        await handle_message(update, context)
        return
    
    # التحقق إذا كان المستخدم في حالة تسجيل
    if 'awaiting_contact_info' in context.user_data and context.user_data['awaiting_contact_info']:
        await handle_message(update, context)
        return
    
    # إذا لم يكن أي من الحالات السابقة، عرض رسالة مساعدة
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "ℹ️ **مرحباً بك في QuickCashSY!**\n\n"
            "💡 **لبدء الاستخدام، اضغط على /start**\n\n"
            "✨ **أو اختر من الأزرار التالية:**",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🚀 بدء الاستخدام", callback_data="back_to_main"),
                    InlineKeyboardButton("❓ المساعدة", callback_data="support")
                ]
            ]),
            parse_mode='Markdown'
        )

# ============ تشغيل البوت ============
def main():
    print("🚀 بدء تشغيل QuickCashSY...")
    print("💎 منصة الوساطة المالية الآمنة")
    print(f"👤 المسؤول: {ADMIN_ID}")
    print(f"📢 القناة: {CHANNEL_LINK}")
    print(f"🔗 معرف القناة: {CHANNEL_ID}")
    print(f"🏦 محفظة USDT: {BOT_WALLET_ADDRESS}")
    
    print("\n✅ **نظام التسجيل الجديد المعدل**")
    print("📋 **خطوات التسجيل:**")
    print("1. 📜 قبول الشروط والأحكام")
    print("2. 🔗 الانضمام للقناة الرسمية")
    print("3. 📱 مشاركة جهة الاتصال (زر KeyboardButton بنقرة واحدة)")
    print("4. ✅ الوصول الكامل للخدمات")
    
    print("\n🛒 **نظام العروض المحسن:**")
    print("• ✅ إدارة العروض مع أزرار حذف وتعديل")
    print("• 🔄 نظام طلبات المستخدمين")
    print("• 🤝 إشعارات الموافقة على الطلبات")
    print("• 📊 تفاصيل العرض بطريقة احترافية")
    
    print("\n💰 **نظام المعاملات المتكامل:**")
    print("• 🏦 محفظة وسيط آمنة")
    print("• 🔗 إدخال معرف معاملة USDT")
    print("• 📸 إرسال إثباتات الدفع")
    print("• ⚡ إكمال المعاملات تلقائياً")
    print("• 💰 نظام عمولة مرن (0.5 دولار تحت 1000 دولار، 1 دولار فوقها)")
    
    print("\n🛠️ **لوحة تحكم المسؤول الكاملة:**")
    print("• 📊 إحصائيات تفصيلية")
    print("• 🔔 إشعارات ذكية للمسؤول")
    print("• 👥 إدارة المستخدمين المتقدمة")
    print("• 💸 مراجعة المعاملات والطلبات")
    
    print("\n📱 **نظام مشاركة جهة الاتصال المعدل:**")
    print("✅ زر KeyboardButton مع request_contact=True")
    print("✅ مشاركة بنقرة واحدة فقط")
    print("✅ إزالة تلقائية للوحة المفاتيح الظرفية")
    print("✅ تنظيم الرسائل وحذف التلقائي")
    
    db = DatabaseManager()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # 1. معالجة الأوامر
    application.add_handler(CommandHandler("start", handle_start_with_params))
    
    # 2. معالجة callback queries
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # 3. معالجة جهات الاتصال (الأولوية العالية)
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact_received))
    
    # 4. معالجة أزرار ReplyKeyboardMarkup
    application.add_handler(MessageHandler(filters.Regex(r'^📱 مشاركة جهة الاتصال$'), handle_reply_keyboard_buttons))
    
    # 5. معالجة الصور (إثباتات الدفع)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_messages))
    
    # 6. معالجة النصوص (معاملات USDT)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_general_messages))
    
    print("\n✅ جميع الأنظمة جاهزة للتشغيل!")
    print("📊 قاعدة البيانات: quickcash_users.db")
    print("🔗 رابط البوت: https://t.me/Qcss_bot")
    print("📱 افتح البوت على Telegram واضغط /start")
    print("\n🔍 **سجلات التصحيح مفعلة:** سيظهر [DEBUG] عند نشر العروض")
    print("💾 **نسخة البوت المعدلة تعمل بكامل طاقتها!**")
    print("\n" + "="*50)
    print("📈 **الميزات الجديدة المضافة:**")
    print("1. ✅ إدارة العروض (حذف/تعديل)")
    print("2. ✅ نظام طلبات المستخدمين")
    print("3. ✅ إشعارات الموافقة على الطلبات")
    print("4. ✅ ترتيب أزرار الواجهة الرئيسية")
    print("5. ✅ إشعارات المسؤول الذكية")
    print("6. ✅ نظام الوساطة المالية الآمن")
    print("7. ✅ محفظة وسيط ودفع عمولات")
    print("="*50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
