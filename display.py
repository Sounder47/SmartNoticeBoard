from flask import Flask, render_template, request, redirect, url_for
import os, json

# --------------------------
# Paths
# --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
DATA_FILE = os.path.join(BASE_DIR, "notices.json")

# --------------------------
# Flask App
# --------------------------
app = Flask(__name__, template_folder=TEMPLATE_DIR)

# --------------------------
# Helper Functions
# --------------------------
def load_notices():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_notices(notices):
    with open(DATA_FILE, "w") as f:
        json.dump(notices, f, indent=4)

# --------------------------
# Display Page
# --------------------------
@app.route("/")
def index():
    notices = load_notices()
    return render_template("index.html", notices=notices)

# --------------------------
# Admin Page
# --------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]

        notices = load_notices()
        notices.insert(0, {"title": title, "description": description})
        save_notices(notices)

        return redirect(url_for("admin"))

    return render_template("admin.html")

# --------------------------
# Run Flask App
# --------------------------
if __name__ == "__main__":
    # host=0.0.0.0 makes it accessible externally
    # port from env for hosting platforms
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))