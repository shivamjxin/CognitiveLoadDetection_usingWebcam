from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app, cors_allowed_origins="*")  # !!!CHANGE LATER!!! '*' allows any platform to inject data into our server 

@app.route('/')
def hello_world():
    return "hello!"

@socketio.on('cv_frame')  # keeps the function on idle but the moment data is transmitted from camera_engine the function gets data shoved into it
def receive_cv_data(data):
    pass

if __name__ == '__main__':
    socketio.run(app, port = 5000)