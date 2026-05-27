from flask import Flask,render_template,request,redirect,session,jsonify
import sqlite3
import random
import string
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key="valorantboost"

UPLOAD_FOLDER = "static/proof"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# =========================
# DATABASE
# =========================

def db():
    return sqlite3.connect("boost.db",check_same_thread=False)

# =========================
# RANK SYSTEM
# =========================

RANK_ORDER = [
"iron1","iron2","iron3",
"bronze1","bronze2","bronze3",
"silver1","silver2","silver3",
"gold1","gold2","gold3",
"platinum1","platinum2","platinum3",
"diamond1","diamond2","diamond3",
"ascendant1","ascendant2","ascendant3",
"immortal1","immortal2","immortal3"
]

# =========================
# INIT DATABASE
# =========================

def init():

    conn=db()
    c=conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT,
    wallet INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT,
    riot_id TEXT,
    riot_pass TEXT,
    rank_from TEXT,
    rank_to TEXT,
    price INTEGER,
    staff TEXT,
    status TEXT,
    proof TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS coupons(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    discount INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS coupon_used(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    coupon_code TEXT
    )
    """)

    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES(NULL,'admin','admin123','admin',0)")

    conn.commit()
    conn.close()

init()

# =========================
# HOME
# =========================

@app.route("/")
def home():

    conn=db()
    c=conn.cursor()

    # 📦 ออเดอร์วันนี้ (เอาง่ายก่อน)
    c.execute("SELECT COUNT(*) FROM orders")
    today_orders = c.fetchone()[0]

    # 👨‍💻 staff ทั้งหมด
    c.execute("SELECT COUNT(*) FROM users WHERE role='staff'")
    staff_online = c.fetchone()[0]

    # 🔥 staff ว่าง (queue = ยังไม่มีงาน)
    c.execute("SELECT COUNT(*) FROM orders WHERE status='queue'")
    staff_ready = c.fetchone()[0]

    # 💰 ถ้า login อยู่
    wallet = None
    if "user" in session:
        c.execute("SELECT wallet FROM users WHERE username=?", (session["user"],))
        wallet = c.fetchone()[0]
    else:
        wallet = 0  # 🔥 ใส่ตรงนี้
    conn.close()

    return render_template(
        "index.html",
        today_orders=today_orders,
        staff_online=staff_online,
        staff_ready=staff_ready,
        wallet=wallet
    )
# =========================
# CHECK COUPON
# =========================

@app.route("/check_coupon/<code>")
def check_coupon(code):

    if "user" not in session:
        return jsonify({"discount":0})

    username=session["user"]
    code=code.upper()

    conn=db()
    c=conn.cursor()

    c.execute("SELECT discount FROM coupons WHERE UPPER(code)=?",(code,))
    data=c.fetchone()

    if not data:
        conn.close()
        return jsonify({"discount":0})

    discount=data[0]

    c.execute("""
    SELECT * FROM coupon_used
    WHERE username=? AND coupon_code=?
    """,(username,code))

    used=c.fetchone()

    conn.close()

    if used:
        return jsonify({"discount":0})

    return jsonify({"discount":discount})

# =========================
# ORDER BOOST
# =========================
@app.route("/order",methods=["POST"])
def order():

    if "user" not in session:
        return redirect("/login")

    username=session["user"]

    riot_id=request.form["riot"]
    riot_pass=request.form["password"]
    rank_from=request.form["rank_from"]
    rank_to=request.form["rank_to"]
    coupon=request.form.get("coupon","").upper()

    conn=db()
    c=conn.cursor()

    # =========================
    # 🔥 คำนวณราคาใหม่ (กันโกง)
    # =========================

    def get_rank_name(r):
        if "iron" in r: return "iron"
        if "bronze" in r: return "bronze"
        if "silver" in r: return "silver"
        if "gold" in r: return "gold"
        if "platinum" in r: return "platinum"
        if "diamond" in r: return "diamond"
        if "ascendant" in r: return "ascendant"
        return r

    rank_price={
        "iron":10,"bronze":25,"silver":40,"gold":70,
        "platinum":90,"diamond":150,"ascendant":210,
        "immortal1":350,"immortal2":500,"immortal3":750
    }

    start = RANK_ORDER.index(rank_from)
    end = RANK_ORDER.index(rank_to)

    price = 0

    if end <= start:
        conn.close()
        return {"status":"invalid_rank"}

    for i in range(start,end):
        next_rank = RANK_ORDER[i+1]
        price += rank_price[get_rank_name(next_rank)]

    # =========================
    # 🎟️ ตรวจคูปอง
    # =========================

    discount = 0

    if coupon:

        # 🔍 มีคูปองไหม
        c.execute("SELECT discount FROM coupons WHERE code=?", (coupon,))
        data = c.fetchone()

        if not data:
            conn.close()
            return {"status":"invalid_coupon"}

        # 🔥 ใช้ไปแล้วหรือยัง
        c.execute("""
        SELECT * FROM coupon_used
        WHERE username=? AND coupon_code=?
        """,(username,coupon))

        used = c.fetchone()

        if used:
            conn.close()
            return {"status":"used_coupon"}

        discount = data[0]

    # =========================
    # 💰 ราคาสุดท้าย
    # =========================

    final_price = price - discount
    if final_price < 0:
        final_price = 0

    # =========================
    # 💰 เช็คเงิน
    # =========================

    c.execute("SELECT wallet FROM users WHERE username=?", (username,))
    wallet=c.fetchone()[0]

    if wallet < final_price:
        conn.close()
        return {"status":"nomoney"}

    new_wallet = wallet - final_price

    # =========================
    # 💾 อัปเดต DB
    # =========================

    c.execute(
        "UPDATE users SET wallet=? WHERE username=?",
        (new_wallet,username)
    )

    c.execute("""
    INSERT INTO orders
    (customer,riot_id,riot_pass,rank_from,rank_to,price,staff,status)
    VALUES (?,?,?,?,?,?,?,?)
    """,(username,riot_id,riot_pass,rank_from,rank_to,final_price,"-","queue"))

    # 🔥 บันทึกว่าใช้คูปองแล้ว (หลังผ่านทุกอย่าง)
    if coupon:
        c.execute(
            "INSERT INTO coupon_used (username,coupon_code) VALUES (?,?)",
            (username,coupon)
        )

    conn.commit()
    conn.close()

    return {"status":"success"}

# =========================
# STAFF PANEL
# =========================

@app.route("/staff")
def staff():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "staff":
        return redirect("/")

    page=request.args.get("page","queue")

    conn=db()
    c=conn.cursor()

    c.execute("SELECT wallet FROM users WHERE username=?", (session["user"],))
    wallet=c.fetchone()[0]

    c.execute("SELECT * FROM orders WHERE status='queue'")
    queue=c.fetchall()

    c.execute("SELECT * FROM orders WHERE staff=?", (session["user"],))
    myorders=c.fetchall()

    conn.close()

    return render_template(
        "staff.html",
        queue=queue,
        myorders=myorders,
        wallet=wallet,
        page=page
    )

# =========================
# TAKE ORDER
# =========================

@app.route("/take_order/<int:order_id>")
def take_order(order_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "staff":
        return redirect("/")

    conn=db()
    c=conn.cursor()

    c.execute("SELECT status FROM orders WHERE id=?", (order_id,))
    order=c.fetchone()

    if not order:
        conn.close()
        return redirect("/staff")

    status=order[0]

    if status != "queue":
        conn.close()
        return redirect("/staff?page=queue")

    c.execute("""
    UPDATE orders
    SET status='working', staff=?
    WHERE id=? AND status='queue'
    """,(session["user"],order_id))

    conn.commit()
    conn.close()

    return redirect("/staff?page=myorders")

# =========================
# ADMIN PANEL
# =========================

@app.route("/admin")
def admin():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return redirect("/")

    page=request.args.get("page","users")

    conn=db()
    c=conn.cursor()

    c.execute("SELECT * FROM users")
    users=c.fetchall()

    c.execute("SELECT * FROM orders")
    orders=c.fetchall()

    c.execute("SELECT * FROM coupons")
    coupons=c.fetchall()

    c.execute("SELECT wallet FROM users WHERE username=?", (session["user"],))
    wallet=c.fetchone()[0]

    conn.close()

    return render_template("admin.html",
    users=users,
    orders=orders,
    coupons=coupons,
    page=page,
    wallet=wallet)

# =========================
# CHANGE ROLE
# =========================

@app.route("/role",methods=["POST"])
def change_role():

    if session["role"]!="admin":
        return redirect("/")

    user=request.form["user"]
    role=request.form["role"]

    conn=db()
    c=conn.cursor()

    c.execute("UPDATE users SET role=? WHERE username=?", (role,user))

    conn.commit()
    conn.close()

    return redirect("/admin?page=users")

# =========================
# DELETE USER
# =========================

@app.route("/delete/<username>")
def delete_user(username):

    if session["role"]!="admin":
        return redirect("/")

    conn=db()
    c=conn.cursor()

    c.execute("DELETE FROM users WHERE username=?", (username,))

    conn.commit()
    conn.close()

    return redirect("/admin?page=users")

# =========================
# GENERATE COUPON
# =========================

@app.route("/generate_coupon",methods=["POST"])
def generate_coupon():

    if session["role"]!="admin":
        return redirect("/")

    discount=int(request.form["discount"])

    letters = string.ascii_uppercase + string.digits
    code = "BOOST-" + ''.join(random.choice(letters) for i in range(4))

    conn=db()
    c=conn.cursor()

    c.execute(
        "INSERT INTO coupons (code,discount) VALUES (?,?)",
        (code,discount)
    )

    conn.commit()
    conn.close()

    return redirect("/admin?page=coupons")

# =========================
# LOGIN
# =========================

@app.route("/login",methods=["GET","POST"])
def login():

    error=None

    if request.method=="POST":

        user=request.form["username"]
        pw=request.form["password"]

        conn=db()
        c=conn.cursor()

        c.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (user,pw)
        )

        data=c.fetchone()
        conn.close()

        if data:

            session["user"]=data[1]
            session["role"]=data[3]

            if data[3]=="admin":
                return redirect("/admin")

            if data[3]=="staff":
                return redirect("/staff")

            return redirect("/")

        else:
            error="Login Failed"

    return render_template("login.html",error=error)

# =========================
# MONEY SYSTEM
# =========================

@app.route("/money", methods=["POST"])
def money():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return redirect("/")

    username = request.form["user"]
    amount = int(request.form["amount"])

    conn = db()
    c = conn.cursor()

    c.execute("""
    UPDATE users
    SET wallet = wallet + ?
    WHERE username=?
    """,(amount,username))

    conn.commit()
    conn.close()

    return redirect("/admin?page=users")

# =========================
# REGISTER (🔥 แก้ popup)
# =========================

@app.route("/register",methods=["GET","POST"])
def register():

    error=None

    if request.method=="POST":

        user=request.form["username"]
        pw=request.form["password"]
        confirm=request.form["confirm"]

        if pw!=confirm:
            error="Password not match"

        else:

            conn=db()
            c=conn.cursor()

            try:

                c.execute(
                "INSERT INTO users VALUES(NULL,?,?,?,?)",
                (user,pw,"member",0)
                )

                conn.commit()
                conn.close()

                return redirect("/login?success=1")

            except sqlite3.IntegrityError:
                conn.rollback()   # 🔥 สำคัญมาก
                conn.close()      # 🔥 ต้องปิด

                error="Username นี้มีคนใช้แล้ว"

            except Exception as e:
                conn.rollback()
                conn.close()

                error="เกิดข้อผิดพลาด"

    return render_template("register.html",error=error)

# =========================
# TOPUP (🔥 เพิ่ม)
# =========================

@app.route("/topup")
def topup():

    if "user" not in session:
        return redirect("/login")

    conn=db()
    c=conn.cursor()

    c.execute("SELECT wallet FROM users WHERE username=?", (session["user"],))
    wallet=c.fetchone()[0]

    conn.close()

    return render_template("topup.html",wallet=wallet)

# =========================
# CONTACT (🔥 เพิ่ม)
# =========================

@app.route("/contact")
def contact():

    if "user" not in session:
        return redirect("/login")

    return render_template("contact.html")

# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():
    session.clear()  # 🔥 ล้าง session ทั้งหมด
    return redirect("/")  # 🔥 กลับหน้า index

# =========================
# FINISH ORDER
# =========================

@app.route("/finish_order/<int:order_id>", methods=["POST"])
def finish_order(order_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "staff":
        return redirect("/")

    file = request.files.get("proof")

    if not file or file.filename == "":
        return "ต้องแนบรูปก่อนจบงาน"

    filename = secure_filename(file.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    conn=db()
    c=conn.cursor()

    c.execute("SELECT price,staff FROM orders WHERE id=?", (order_id,))
    data=c.fetchone()

    if not data:
        conn.close()
        return redirect("/staff")

    price=data[0]
    staff=data[1]

    staff_money = int(price * 0.8)
    admin_money = int(price * 0.2)

    c.execute("""
    UPDATE users
    SET wallet = wallet + ?
    WHERE username=?
    """,(staff_money,staff))

    c.execute("""
    UPDATE users
    SET wallet = wallet + ?
    WHERE role='admin'
    """,(admin_money,))

    c.execute("""
    UPDATE orders
    SET status='done', proof=?
    WHERE id=?
    """,(filename,order_id))

    conn.commit()
    conn.close()

    return redirect("/staff?page=myorders")

app.run(host='0.0.0.0')