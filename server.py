from flask import Flask, request
from flask_restful import Resource, Api
from json import dumps
from flask_jsonpify import jsonify

from mppsolar.mpputils import mppUtils

app = Flask(__name__)
api = Api(app)

device='/dev/ttyUSB0'
baud=2400
host='0.0.0.0'
port='5002'

mp = mppUtils(device, baud)

class Status(Resource):
  def get(self):
    data = mp.getResponseDict("Q1")
    data.update(mp.getResponseDict("QPIGS"))
    status = {}
    for item in data.keys():
        status[key] = data[key][0]
    return data

api.add_resource(Status, '/status') # Route_1

if __name__ == '__main__':
     app.run(host= host, port=port)
