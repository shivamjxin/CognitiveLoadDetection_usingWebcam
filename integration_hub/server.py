from flask import Flask, render_template
from flask_socketio import SocketIO
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app, cors_allowed_origins="*")  # !!!CHANGE LATER!!! '*' allows any platform to inject data into our server 

@app.route('/')
def hello_world():
    return "hello!"

cv_log_file = open("../data_logs/raw_cv_stream.jsonl","a")

@socketio.on('cv_frame')  # keeps the function on idle but the moment data is transmitted from camera_engine the function gets data shoved into it
def receive_cv_data(data):
    cv_stream = json.dumps(data)
    cv_log_file.write(cv_stream + "\n")
    cv_log_file.flush()


if __name__ == '__main__':
    socketio.run(app, port = 5000)