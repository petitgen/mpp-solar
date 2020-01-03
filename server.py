from flask import Flask, request
from flask_restful import Resource, Api
from json import dumps
from flask.ext.jsonpify import jsonify

from mpputils import mppUtils

app = Flask(__name__)
api = Api(app)

device="/dev/ttyUSB0"
baud=2400

mp = mppUtils(device, baud)

class Status(Resource):
  def get(self):
    data = mp.getResponseDict("Q1")
    data.update(mp.getResponseDict("QPIGS"))
    return data

api.add_resource(Status, '/status') # Route_1

if __name__ == '__main__':
     app.run(port='5002')
