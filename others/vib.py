from flask import Flask
import subprocess

app = Flask(__name__)

@app.route('/vib/<int:time>')
def get_user(time):
    if time <= 50:
        return {'status': 'err:时间过短', 'time': time}
    if time >= 30000:
        return {'status': 'err:时间过长', 'time': time}
    subprocess.run(['termux-vibrate', '-d', str(time)])
    return {'status': 'ok', 'time': time}

if __name__ =="__main__":
    app.run(host="127.0.0.1",port=1145,debug=True)