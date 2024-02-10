import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Create new table, and index (for efficient search later on) to keep track of stock orders, by each user
db.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER, user_id NUMERIC NOT NULL, symbol TEXT NOT NULL, \
            shares NUMERIC NOT NULL, price NUMERIC NOT NULL, timestamp TEXT, PRIMARY KEY(id), \
            FOREIGN KEY(user_id) REFERENCES users(id))")
db.execute("CREATE INDEX IF NOT EXISTS orders_by_user_id_index ON orders (user_id)")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Check the current portfolio
    owns = own_shares()
    total = 0
    for symbol, shares in owns.items():
        quote = lookup(symbol)
        name, price = quote["name"], quote["price"]
        stock_value = shares * price
        total += stock_value
        owns[symbol] = (name, shares, usd(price), usd(stock_value))
    cash = db.execute("SELECT cash FROM users WHERE id = ? ", session["user_id"])[0]['cash']
    total += cash
    return render_template("index.html", owns=owns, cash=usd(cash), total=usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))

        # Ensure stock symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol")

        # Ensure that stock is valid
        if not quote:
            return apology("invalid symbol")

        # Ensure amount of shares was submitted
        if not request.form.get("shares"):
            return apology("missing shares")

        # Ensure inputed number of shares is not an alphabetical string
        if not str.isdigit(request.form.get("shares")):
            return apology("invalid shares")

         # Ensure number of shares is a positive integer
        if int(request.form.get("shares")) <= 0:
            return apology("invalid shares")

        price = quote["price"]
        symbol = quote["symbol"]
        shares = int(request.form.get("shares"))
        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']

        # Check if user has enough money
        remain = cash - price * shares
        if remain < 0:
            return apology(" Balance Insufficient. Failed Purchase.")
        else:
            # Update amount of cash the user has after purchase
            db.execute("UPDATE users SET cash = ? WHERE id = ?", remain, user_id)

            db.execute("INSERT INTO orders (user_id, symbol, shares, price, timestamp) VALUES (?, ?, ?, ?, ?)",
                       user_id, symbol, shares, price, time_now())
            return redirect("/")
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # select values from db about user's transactions
    rows = db.execute("SELECT symbol, shares, price, timestamp FROM orders WHERE user_id = ?", session["user_id"])
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Lookup the stock
        quote = lookup(request.form.get("symbol"))

        # Ensure symbol for quoting stock was submitted
        if not request.form.get("symbol"):
            return apology("Missing symbol", 400)

        # If lookup fails, return error
        if not quote:
            return apology("Invalid symbol", 400)

        # Else return the info received
        else:
            return render_template("quoted.html", name=quote["name"], price=usd(quote["price"]), symbol=quote["symbol"])

    # User reached route via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure retyped password was submitted
        if not request.form.get("confirmation"):
            return apology("must retype password in field", 400)

        # Ensure passwords submitted in fields were the same
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("must enter same password in both fields", 400)

        # Ensure username doesn't already exist
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) == 1:
            return apology("username already exists", 400)

        # Get all info from the form
        hash = generate_password_hash(request.form.get("password"))

        # Add the user's entry into the database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"), hash)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    owns = own_shares()

    # ensure request methon is POST
    if request.method == "POST":

        # lookup a stock's current price using a function "lookup" implemented in helpers.py
        quote = lookup(request.form.get("symbol"))

        # ensure stock symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # ensure that stock is valid
        if not quote:
            return apology("invalid symbol", 400)

        # ensure amout of shares was submitted
        if not request.form.get("shares"):
            return apology("missing shares", 400)

        # ensure number of shares is numeric
        if not str.isdigit(request.form.get("shares")):
            return apology("invalid shares", 400)

        # ensure number of shares is a positive integer
        if int(request.form.get("shares")) <= 0:
            return apology("invalid shares", 400)

        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        if owns[symbol] < shares:
            return apology("insufficent shares", 400)

        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']
        price = quote["price"]
        remain = cash + price * shares
        db.execute("UPDATE users SET cash = ? WHERE id = ?", remain, user_id)
        # Log the transaction into orders
        db.execute("INSERT INTO orders (user_id, symbol, shares, price, timestamp) VALUES (?, ?, ?, ?, ?)",
                   user_id, symbol, -shares, price, time_now())

        return redirect("/")

    # else if user reached rout via GET(as by clicking a link or via redirect)
    else:
        return render_template("sell.html")


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change user password"""

    if request.method == "POST":

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # ensure username exists and password is correct
        elif len(rows) != 1 or not check_password_hash(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # ensure new password was submitted
        elif not request.form.get("new password"):
            return apology("must provide new password")

        # ensure new password does not repeat old password
        elif request.form.get("password") == request.form.get("new password"):
            return apology("new password can't repeat old password")

        # ensure new password was subbmited again
        elif not request.form.get("new password (again)"):
            return apology("must repeat new password one more time")

        # ensure passwords match
        elif request.form.get("new password") != request.form.get("new password (again)"):
            return apology("Passwords don't match. Try again!")

        db.execute("UPDATE users SET hash = :hash WHERE id = :id", hash=generate_password_hash(
            request.form.get("new password")), id=session["user_id"])

        flash("Congratulations! Password has been changed!")

        # redirect user to home page
        return redirect("/")

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("change_password.html")


def own_shares():
    """Helper function: Which stocks the user owns, and numbers of shares owned. Return: dictionary {symbol: qty}"""
    user_id = session["user_id"]
    owns = {}
    query = db.execute("SELECT symbol, shares FROM orders WHERE user_id = ?", user_id)
    for q in query:
        symbol, shares = q["symbol"], q["shares"]
        owns[symbol] = owns.setdefault(symbol, 0) + shares
    # filter zero-share stocks
    owns = {k: v for k, v in owns.items() if v != 0}
    return owns


def time_now():
    """HELPER: get current UTC date and time"""
    now_utc = datetime.now(timezone.utc)
    return str(now_utc.date()) + ' @time ' + now_utc.time().strftime("%H:%M:%S")
