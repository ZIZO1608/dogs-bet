"""All user-facing text, Arabic + English. Messages use Telegram HTML formatting."""

TEXTS: dict[str, dict[str, str]] = {
    "ar": {
        # onboarding
        "choose_lang": "🐶 أهلاً بك في <b>{store}</b>\nاختر لغتك:\nChoose your language:",
        "terms": (
            "📜 <b>شروط استخدام {store}</b>\n\n"
            "1️⃣ البوت مخصّص لإنشاء حسابات المنصة وشحن الرصيد فقط.\n"
            "2️⃣ ممنوع قلب الرصيد أو أي تلاعب — الحظر نهائي.\n"
            "3️⃣ شحن الرصيد يتم بعد التحقق من التحويل من قبل الإدارة.\n"
            "4️⃣ إرسال إيصالات مزوّرة أو مكرّرة يؤدي إلى حظر الحساب نهائياً.\n"
            "5️⃣ تأكد من بياناتك قبل أي عملية.\n\n"
            "باستخدامك البوت فأنت توافق على هذه الشروط ✅"
        ),
        "terms_join": "\n\n📢 للمتابعة يجب الانضمام إلى قنواتنا:",
        "btn_accept": "✅ موافق ومتابعة",
        "btn_accept_join": "✅ انضممت وموافق",
        "btn_channel": "📢 {channel}",
        "not_joined": "⚠️ لازم تنضم لكل القنوات أولاً، بعدين اضغط الزر مرة ثانية.",
        "welcome": (
            "🐶 <b>Dogs Bet</b>\n"
            "أهلاً <b>{name}</b>!\n"
            "💳 رصيد البوت: <b>{balance}</b>\n\n"
            "اختر من القائمة 👇"
        ),
        "banned": "⛔️ حسابك محظور. للتواصل: {support}",

        # main menu (Wolf style)
        "m_create_account": "🐶  إنشاء حساب Dogs",
        "m_my_accounts": "📋  حساباتي",
        "m_topup": "💳  شحن",
        "m_withdraw": "💸  سحب",
        "m_balances": "📊  الأرصدة",
        "m_support": "🆘  الدعم",
        "m_terms_channels": "📜  الشروط",
        "m_offers": "🎁  العروض",
        "m_referrals": "👥  الإحالات",
        "m_gift": "🎟  كود هدية",
        "m_website": "🌐  الموقع",
        "m_lang": "🌐 English",
        "m_admin": "🛠  الإدارة",

        # create account
        "create_title": "🐶 <b>إنشاء حساب جديد</b>\n\nسيتم إنشاء حساب لك على المنصة.",
        "create_ask_username": "✍️ أرسل اسم المستخدم\n(حروف وأرقام فقط، 3-20)\n\nأو اضغط الزر للتوليد التلقائي 👇",
        "create_username_invalid": "⚠️ استخدم حروف وأرقام فقط (3-20).\nمثال: dog123 أو zizo2026",
        "create_username_taken": "⚠️ هذا الاسم مستخدم مسبقاً، جرّب اسماً آخر.",
        "create_success": (
            "✅ تم إنشاء حسابك بنجاح!\n\n"
            "👤 المستخدم: <code>{username}</code>\n"
            "🔑 كلمة المرور: <code>{password}</code>\n\n"
            "⚠️ احفظ كلمة المرور في مكان آمن."
        ),
        "accounts_empty": "You have no accounts yet. Tap Create account.",
        "accounts_list": "📋 حساباتك على المنصة:\n\n{list}",
        "accounts_item": "👤 <code>{username}</code>\n🔑 <code>{password}</code>\n",
        "create_already": "يمكنك إنشاء حسابات إضافية من نفس البوت.",
        "create_coming": "⏳ إنشاء الحسابات عبر الـ API قريباً. تواصل مع الدعم حالياً.",

        # balances
        "balances_title": (
            "📊 <b>أرصدتك</b>\n\n"
            "💳 رصيد البوت: <b>{bot_balance}</b>\n"
            "🏟 رصيد الموقع: <b>{site_balance}</b>\n\n"
            "سعر الإيداع: {rate}"
        ),

        # topup
        "topup_title": "💳 <b>شحن رصيد البوت</b>\n\nرصيدك الحالي: <b>{balance}</b>\nالحد الأدنى: {min}\n\nاختر طريقة الدفع:",
        "topup_empty": "لا توجد طرق دفع متاحة حالياً.",
        "topup_details": (
            "💳 <b>{method}</b>\n\n"
            "{details}\n\n"
            "الحد الأدنى: {min}\n\n"
            "✍️ أرسل <b>المبلغ</b> الذي حوّلته ({currency}):"
        ),
        "amount_invalid": "⚠️ أرسل رقماً صحيحاً فقط، مثال: 25",
        "ask_txn": "🔢 أرسل <b>رقم العملية</b> (Transaction ID) الموجود في إيصال التحويل:",
        "ask_proof": "📸 أرسل <b>صورة الإيصال</b> (أو اكتب تخطي إذا لم تكن مطلوبة):",
        "proof_invalid": "⚠️ أرسل صورة الإيصال كصورة، أو اكتب تخطي.",
        "deposit_created": "✅ تم استلام طلب الشحن <b>#{id}</b>\nالمبلغ: {amount}\nسيتم التحقق وإضافة الرصيد قريباً ⏳",
        "deposit_approved": "✅ تمت الموافقة على الشحن <b>#{id}</b>\nأُضيف <b>{credited}</b> إلى رصيدك.\nرصيدك الآن: <b>{balance}</b>",
        "deposit_rejected": "❌ تم رفض طلب الشحن <b>#{id}</b>. للاستفسار تواصل مع الدعم: {support}",

        # withdraw
        "withdraw_title": "💸 <b>سحب رصيد البوت</b>\n\nرصيدك: <b>{balance}</b>\nالحد الأدنى للسحب: {min}\n\nاختر طريقة السحب:",
        "withdraw_empty": "لا توجد طرق سحب متاحة حالياً.",
        "withdraw_ask_amount": "✍️ أرسل المبلغ الذي تريد سحبه (بالدولار):",
        "withdraw_ask_dest": "✍️ أرسل عنوان المحفظة / رقم الحساب الذي تريد السحب إليه:",
        "withdraw_created": "✅ تم إنشاء طلب السحب <b>#{id}</b>\nالمبلغ: {amount}\nسيتم مراجعته قريباً ⏳",
        "withdraw_approved": "✅ تم تنفيذ سحبك <b>#{id}</b>\nالمبلغ: {amount}",
        "withdraw_rejected": "❌ تم رفض طلب السحب <b>#{id}</b> وإعادة المبلغ لرصيدك.{note}",
        "withdraw_insufficient": "⚠️ رصيدك غير كافٍ للسحب.",

        # gift
        "gift_ask": "🎟 أرسل <b>كود الهدية</b>:",
        "gift_success": "✅ تم تفعيل الكود!\nأُضيف <b>{amount}</b> إلى رصيدك.\nرصيدك الآن: <b>{balance}</b>",
        "gift_invalid": "⚠️ الكود غير صالح أو منتهي أو مستخدم مسبقاً.",
        "gift_already": "⚠️ لقد استخدمت هذا الكود من قبل.",

        # referrals
        "referrals_title": (
            "👥 <b>نظام الإحالات</b>\n\n"
            "رابطك الخاص:\n<code>{link}</code>\n\n"
            "عدد المدعوين: <b>{count}</b>\n"
            "الأرباح: <b>{earnings}</b>"
        ),

        # offers
        "offers_title": "🎁 <b>العروض الحالية</b>\n\n{offers}",
        "offers_empty": "لا توجد عروض حالياً. تابعنا!",

        # website
        "website_msg": "🌐 موقع المنصة:\n{url}",
        "website_empty": "الموقع غير مضاف بعد. تواصل مع الدعم.",

        # terms & channels
        "terms_channels_msg": "{terms}\n\n{channels}",
        "channels_list": "📢 قنواتنا:\n{list}",
        "no_channels": "لا توجد قنوات مضافة حالياً.",

        # common
        "btn_confirm": "✅ تأكيد",
        "btn_cancel": "❌ إلغاء",
        "btn_back": "🔙 رجوع",
        "cancelled": "تم الإلغاء.",
        "support": "🆘 للدعم تواصل معنا: {support}",
        "lang_changed": "✅ تم تغيير اللغة.",
        "st_pending": "⏳ قيد المعالجة",
        "st_approved": "✅ مقبول",
        "st_completed": "✅ تم التنفيذ",
        "st_rejected": "❌ مرفوض",
        "error_generic": "⚠️ حصل خطأ، حاول مرة ثانية.",
        "err_insufficient": "⚠️ رصيدك غير كافٍ.\nرصيدك: {balance} — المطلوب: {needed}",
        "err_duplicate_txn": "⚠️ رقم العملية هذا مستخدم من قبل. إذا كان هناك خطأ تواصل مع الدعم.",
        "err_already_decided": "هذا الطلب تمت معالجته مسبقاً.",
        "err_not_available": "⚠️ هذا العنصر غير متاح حالياً.",
        "err_below_min": "⚠️ المبلغ أقل من الحد الأدنى.",
        "use_menu": "استخدم الأزرار في القائمة 👇",
        "coming_soon": "⏳ هذه الميزة قريباً جداً.",
    },
    "en": {
        "choose_lang": "🐶 Welcome to <b>{store}</b>\nاختر لغتك:\nChoose your language:",
        "terms": (
            "📜 <b>{store} Terms of Use</b>\n\n"
            "1️⃣ This bot is only for creating platform accounts and topping up balance.\n"
            "2️⃣ Balance flipping or any manipulation is forbidden — permanent ban.\n"
            "3️⃣ Top-ups are credited after admin verification of the transfer.\n"
            "4️⃣ Fake or reused receipts result in permanent account ban.\n"
            "5️⃣ Double-check your details before any operation.\n\n"
            "By using the bot you agree to these terms ✅"
        ),
        "terms_join": "\n\n📢 To continue, join our channels:",
        "btn_accept": "✅ Agree and continue",
        "btn_accept_join": "✅ Joined & agree",
        "btn_channel": "📢 {channel}",
        "not_joined": "⚠️ Please join all channels first, then tap the button again.",
        "welcome": (
            "🐶 <b>Dogs Bet</b>\n"
            "Hi <b>{name}</b>!\n"
            "💳 Bot balance: <b>{balance}</b>\n\n"
            "Choose from the menu 👇"
        ),
        "banned": "⛔️ Your account is banned. Contact: {support}",

        "m_create_account": "🐶  Create Account",
        "m_my_accounts": "📋  My Accounts",
        "m_topup": "💳  Top Up",
        "m_withdraw": "💸  Withdraw",
        "m_balances": "📊  Balances",
        "m_support": "🆘  Support",
        "m_terms_channels": "📜  Terms",
        "m_offers": "🎁  Offers",
        "m_referrals": "👥  Referrals",
        "m_gift": "🎟  Gift Code",
        "m_website": "🌐  Website",
        "m_lang": "🌐 العربية",
        "m_admin": "🛠  Admin",

        "create_title": "🐶 <b>Create new account</b>\n\nA platform account will be created for you.",
        "create_ask_username": "✍️ Send a username\n(letters & numbers, 3-20)\n\nOr tap the button to generate one 👇",
        "create_username_invalid": "⚠️ Letters and numbers only (3-20).\nExample: dog123 or zizo2026",
        "create_username_taken": "⚠️ This username is already taken, try another.",
        "create_success": (
            "✅ Account created successfully!\n\n"
            "👤 Username: <code>{username}</code>\n"
            "🔑 Password: <code>{password}</code>\n\n"
            "⚠️ Save the password in a safe place."
        ),
        "accounts_empty": "You have no accounts yet. Tap Create account.",
        "accounts_list": "📋 Your platform accounts:\n\n{list}",
        "accounts_item": "👤 <code>{username}</code>\n🔑 <code>{password}</code>\n",
        "create_already": "You can create more accounts from the same bot.",
        "create_coming": "⏳ Account creation via API coming soon. Contact support for now.",

        "balances_title": (
            "📊 <b>Your balances</b>\n\n"
            "💳 Bot balance: <b>{bot_balance}</b>\n"
            "🏟 Site balance: <b>{site_balance}</b>\n\n"
            "Deposit rate: {rate}"
        ),

        "topup_title": "💳 <b>Top up bot balance</b>\n\nCurrent balance: <b>{balance}</b>\nMinimum: {min}\n\nChoose a payment method:",
        "topup_empty": "No payment methods available right now.",
        "topup_details": (
            "💳 <b>{method}</b>\n\n"
            "{details}\n\n"
            "Minimum: {min}\n\n"
            "✍️ Send the <b>amount</b> you transferred ({currency}):"
        ),
        "amount_invalid": "⚠️ Send a whole number only, e.g. 25",
        "ask_txn": "🔢 Send the <b>transaction ID</b> from your transfer receipt:",
        "ask_proof": "📸 Send a <b>photo of the receipt</b> (or type skip if not required):",
        "proof_invalid": "⚠️ Please send the receipt as a photo, or type skip.",
        "deposit_created": "✅ Top-up request <b>#{id}</b> received\nAmount: {amount}\nIt will be verified and credited soon ⏳",
        "deposit_approved": "✅ Top-up <b>#{id}</b> approved\n<b>{credited}</b> was added to your balance.\nBalance now: <b>{balance}</b>",
        "deposit_rejected": "❌ Top-up request <b>#{id}</b> was rejected. Questions? Contact support: {support}",

        "withdraw_title": "💸 <b>Withdraw bot balance</b>\n\nYour balance: <b>{balance}</b>\nMinimum withdrawal: {min}\n\nChoose withdrawal method:",
        "withdraw_empty": "No withdrawal methods available right now.",
        "withdraw_ask_amount": "✍️ Send the amount you want to withdraw (in USD):",
        "withdraw_ask_dest": "✍️ Send the wallet address / account number to withdraw to:",
        "withdraw_created": "✅ Withdrawal request <b>#{id}</b> created\nAmount: {amount}\nIt will be reviewed soon ⏳",
        "withdraw_approved": "✅ Your withdrawal <b>#{id}</b> was completed\nAmount: {amount}",
        "withdraw_rejected": "❌ Withdrawal request <b>#{id}</b> was rejected and the amount returned to your balance.{note}",
        "withdraw_insufficient": "⚠️ Not enough balance to withdraw.",

        "gift_ask": "🎟 Send the <b>gift code</b>:",
        "gift_success": "✅ Code activated!\n<b>{amount}</b> was added to your balance.\nBalance now: <b>{balance}</b>",
        "gift_invalid": "⚠️ Invalid, expired, or already used code.",
        "gift_already": "⚠️ You already used this code.",

        "referrals_title": (
            "👥 <b>Referral system</b>\n\n"
            "Your personal link:\n<code>{link}</code>\n\n"
            "Invited: <b>{count}</b>\n"
            "Earnings: <b>{earnings}</b>"
        ),

        "offers_title": "🎁 <b>Current offers</b>\n\n{offers}",
        "offers_empty": "No offers right now. Stay tuned!",

        "website_msg": "🌐 Platform website:\n{url}",
        "website_empty": "Website not set yet. Contact support.",

        "terms_channels_msg": "{terms}\n\n{channels}",
        "channels_list": "📢 Our channels:\n{list}",
        "no_channels": "No channels added yet.",

        "btn_confirm": "✅ Confirm",
        "btn_cancel": "❌ Cancel",
        "btn_back": "🔙 Back",
        "cancelled": "Cancelled.",
        "support": "🆘 Contact support: {support}",
        "lang_changed": "✅ Language changed.",
        "st_pending": "⏳ Pending",
        "st_approved": "✅ Approved",
        "st_completed": "✅ Completed",
        "st_rejected": "❌ Rejected",
        "error_generic": "⚠️ Something went wrong, please try again.",
        "err_insufficient": "⚠️ Not enough balance.\nBalance: {balance} — needed: {needed}",
        "err_duplicate_txn": "⚠️ This transaction ID was already used. If that's a mistake, contact support.",
        "err_already_decided": "This request was already processed.",
        "err_not_available": "⚠️ This item isn't available right now.",
        "err_below_min": "⚠️ The amount is below the minimum.",
        "use_menu": "Use the menu buttons 👇",
        "coming_soon": "⏳ This feature is coming very soon.",
    },
}


def t(lang: str | None, key: str, **kwargs) -> str:
    table = TEXTS.get(lang or "ar", TEXTS["ar"])
    template = table.get(key) or TEXTS["en"].get(key) or key
    return template.format(**kwargs) if kwargs else template


MENU_KEYS = (
    "m_create_account",
    "m_my_accounts",
    "m_topup",
    "m_withdraw",
    "m_balances",
    "m_support",
    "m_terms_channels",
    "m_offers",
    "m_referrals",
    "m_gift",
    "m_website",
    "m_lang",
    "m_admin",
)


def both(key: str) -> tuple[str, str]:
    return (TEXTS["ar"][key], TEXTS["en"][key])


def menu_texts() -> set[str]:
    texts: set[str] = set()
    for lang in TEXTS.values():
        for key in MENU_KEYS:
            if key in lang:
                texts.add(lang[key])
    return texts
