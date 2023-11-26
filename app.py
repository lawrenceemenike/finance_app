import os


from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Fetch user's current cash balance
    rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    cash = rows[0]["cash"] if rows else 0

    # Fetch user's holdings
    holdings = db.execute("SELECT symbol, shares FROM holdings WHERE user_id = :id", id=session["user_id"])

    # Calculate the total value of each holding and total portfolio value
    total_portfolio_value = cash
    portfolio = []

    for holding in holdings:
        symbol = holding["symbol"]
        shares = holding["shares"]
        stock = lookup(symbol)
        if stock:
            total_value = shares * stock["price"]
            total_portfolio_value += total_value
            portfolio.append({"symbol": symbol, "shares": shares, "price": stock["price"], "total": total_value})

    return render_template("index.html", cash=cash, portfolio=portfolio, total_portfolio_value=total_portfolio_value)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("Shares must be a positive integer", 400)

        if shares <= 0:
            return apology("Shares must be a positive integer", 400)

        stock = lookup(symbol)
        if stock is None:
            return apology("Invalid symbol", 400)

        user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]
        total_cost = stock["price"] * shares

        if total_cost > user_cash:
            return apology("Not enough funds", 400)

        # Update transactions and holdings
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, type) VALUES (:user_id, :symbol, :shares, :price, 'buy')",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=stock["price"])

        # Update user's cash
        db.execute("UPDATE users SET cash = cash - :cost WHERE id = :user_id", cost=total_cost, user_id=session["user_id"])

        # Update holdings
        existing_shares = db.execute("SELECT shares FROM holdings WHERE user_id = :user_id AND symbol = :symbol",
                                     user_id=session["user_id"], symbol=symbol)
        if not existing_shares:
            db.execute("INSERT INTO holdings (user_id, symbol, shares) VALUES (:user_id, :symbol, :shares)",
                       user_id=session["user_id"], symbol=symbol, shares=shares)
        else:
            total_shares = existing_shares[0]["shares"] + shares
            db.execute("UPDATE holdings SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol",
                       shares=total_shares, user_id=session["user_id"], symbol=symbol)

        flash("Bought!")
        return redirect("/")
    else:
        return render_template("buy.html")




@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    # Fetch transactions for the logged-in user
    transactions = db.execute("SELECT id, symbol, shares, price, transacted, type FROM transactions WHERE user_id = :user_id ORDER BY transacted DESC", user_id=session["user_id"])

    # Pass the transactions to the history template
    return render_template("history.html", transactions=transactions)


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
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("Missing symbol", 400)

        stock = lookup(symbol)
        if stock is None:
            return apology("Invalid symbol", 400)
        return render_template("quoted.html", stock=stock)
    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Extract form data
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Validation
        if not username:
            return apology("must provide username", 400)
        elif not password:
            return apology("must provide password", 400)
        elif password != confirmation:
            return apology("passwords do not match", 400)

        # Check if username already exists
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
        if len(rows) > 0:
            return apology("username already exists", 400)

        # Password Hashing
        hash_password = generate_password_hash(password)

        # Database Insertion
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash_password)

        # Redirect to home page after successful registration
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        try:
            shares_to_sell = int(request.form.get("shares"))
        except ValueError:
            return apology("Shares must be a positive integer", 400)

        if shares_to_sell <= 0:
            return apology("Shares must be a positive integer", 400)

        # Check if the user has enough shares
        rows = db.execute("SELECT shares FROM holdings WHERE user_id = :user_id AND symbol = :symbol", user_id=session["user_id"], symbol=symbol)
        if not rows or rows[0]["shares"] < shares_to_sell:
            return apology("Not enough shares", 400)

        stock = lookup(symbol)
        if stock is None:
            return apology("Invalid symbol", 400)

        # Process the sale
        total_sale = stock["price"] * shares_to_sell
        db.execute("UPDATE users SET cash = cash + :total_sale WHERE id = :user_id", total_sale=total_sale, user_id=session["user_id"])
        db.execute("UPDATE holdings SET shares = shares - :shares_to_sell WHERE user_id = :user_id AND symbol = :symbol", shares_to_sell=shares_to_sell, user_id=session["user_id"], symbol=symbol)
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, type) VALUES (:user_id, :symbol, -:shares_to_sell, :price, 'sell')", user_id=session["user_id"], symbol=symbol, shares_to_sell=shares_to_sell, price=stock["price"])

        # Remove holding if shares reach 0
        db.execute("DELETE FROM holdings WHERE user_id = :user_id AND symbol = :symbol AND shares = 0", user_id=session["user_id"], symbol=symbol)

        return redirect("/")
    else:
        # Retrieve user's holdings for the form
        holdings = db.execute("SELECT symbol FROM holdings WHERE user_id = :user_id", user_id=session["user_id"])
        return render_template("sell.html", holdings=holdings)


@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    """Compare two stocks."""
    if request.method == "POST":
        symbol1 = request.form.get("symbol1").upper()
        symbol2 = request.form.get("symbol2").upper()

        # Lookup the current prices
        stock1 = lookup(symbol1)
        stock2 = lookup(symbol2)

        if not stock1 or not stock2:
            return apology("Invalid symbol(s)", 400)

        # Calculate the percentage change from the beginning of the day
        # Assuming your 'lookup' function can also provide opening prices
        change1 = ((stock1["price"] - stock1["open"]) / stock1["open"]) * 100
        change2 = ((stock2["price"] - stock2["open"]) / stock2["open"]) * 100

        return render_template("comparison_result.html",
                                stock1=stock1,
                                stock2=stock2,
                                change1=change1,
                                change2=change2)

    else:
        return render_template("compare.html")
