## This looks really ugly, could we make it prettier?
from flask import Flask, render_template, session, redirect, url_for, request, flash
from flask_socketio import SocketIO, disconnect
import os
import pyrebase
from dotenv import load_dotenv
from docker_information import docker_manager
from socket_routes import register_socket_routes  # <- changed name!

#Set up Flask and other libraries
app = Flask(__name__)
app.secret_key = os.urandom(24)
sio = SocketIO(app, cors_allowed_origins="*", manage_session=False)
docker_mgr = docker_manager()
load_dotenv(".env")


## Get api values for Firebase from a .env file
config = {
    "apiKey": os.getenv("API_KEY"),
    "authDomain": os.getenv("AUTH_DOMAIN"),
    "projectId": os.getenv("PROJECT_ID"),
    "storageBucket": os.getenv("STORAGE_BUCKET"),
    "messagingSenderId": os.getenv("MESSAGING_SENDER_ID"),
    "appId":os.getenv("APP_ID"),
    "measurementId":os.getenv("MEASUREMENT_ID"),
    "databaseURL":"n/a",
};

## initialize pyrebase with values from environment
firebase = pyrebase.initialize_app(config)
auth = firebase.auth()

## <Insert comment here oz>
register_socket_routes(sio, docker_mgr)

## Homepage of app - varies based on login status
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template("index.html")
    else:
        return render_template("index_not_logged_in.html")

## Login page for app
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template("login.html")

    elif request.method == 'POST':
        ## If already logged in, just redirect to homepage
        if 'user_id' in session:
            return redirect(url_for('index'))
        else:
            try:
                ## Get username and password
                user_id = request.form.get('username')
                user_pwd = request.form.get('password')

                ## Sign in and store status in cookies
                user = auth.sign_in_with_email_and_password(user_id, user_pwd)
                session['user_id'] = user_id
                return redirect(url_for('index'))
            except:
                flash(f"Password incorrect")
                return redirect(url_for('login'))

        return redirect(url_for('index'))

## Logout of app by removing username signed in status
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

## Sign up for app
@app.route('/sign_up',methods=['GET','POST'])
def sign_up():
    if request.method == 'GET':
        return render_template("signup.html")

    elif request.method == 'POST':
        user_id = request.form.get('username')
        user_pwd = request.form.get('password')

        try:
            ## Create new user with email and password
            auth.create_user_with_email_and_password(user_id, user_pwd)

        except Exception as e:
            ## Need to fix error handling
            flash(f"something went wrong :(")
            return redirect(url_for("sign_up"))

        ## Direct to login after user creation
        return redirect(url_for('login'))

## Open editor for docker container
@app.route('/terminal/<container_name>')
def terminal(container_name):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))
    container = docker_mgr.find_container_by_logical_name(user_id, container_name)
    if not container or container.status != "running":
        return redirect(url_for('index'))
    return render_template("terminal.html")

## Run the app
sio.run(app, host="0.0.0.0", port=5000,debug=True)
