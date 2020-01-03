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
    for key in data.keys():
      if isinstance(data[key][0], str):
        if '.' in data[key][0]:
          status[key] = float(data[key][0])
        else:
          status[key] = int(data[key][0])
      else:
        status[key] = data[key][0]
    return jsonify(status)

api.add_resource(Status, '/status') # Route_1

if __name__ == '__main__':
     app.run(host= host, port=port)
