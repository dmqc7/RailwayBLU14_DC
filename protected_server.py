import os
import json
import pickle
import joblib
import pandas as pd
from uuid import uuid4
from flask import Flask, jsonify, request
from peewee import (
    SqliteDatabase, PostgresqlDatabase, Model, IntegerField,
    FloatField, TextField, IntegrityError
)
from playhouse.shortcuts import model_to_dict


########################################
# Begin database stuff

DB = SqliteDatabase('predictions.db')


class Prediction(Model):
    observation_id = IntegerField(unique=True)
    observation = TextField()
    proba = FloatField()
    true_class = IntegerField(null=True)

    class Meta:
        database = DB


DB.create_tables([Prediction], safe=True)

# End database stuff
########################################

########################################
# Unpickle the previously-trained model


with open(os.path.join('data', 'columns.json')) as fh:
    columns = json.load(fh)


with open(os.path.join('data', 'pipeline.pickle'), 'rb') as fh:
    pipeline = joblib.load(fh)


with open(os.path.join('data', 'dtypes.pickle'), 'rb') as fh:
    dtypes = pickle.load(fh)


# End model un-pickling
########################################

########################################
# Input validation functions


def check_request(request):
      
    if "observation_id" not in request:
        error = "Field `observation_id` missing from request: {}".format(request)
        return False, error

    if "data" not in request:
        error = "Field `data` missing from request: {}".format(request)
        return False, error
    
    return True, ""
    

def get_valid_categories(df, column):

    categories = list(df[column].unique())
    # YOUR CODE HERE
    #raise NotImplementedError()

    return categories



def check_valid_column(observation):
            
    valid_columns = {
            "age",
            "sex",
            "race",
            "workclass",
            "education",
            "marital-status",
            "capital-gain",
            "capital-loss",
            "hours-per-week"
            }
    
    keys = set(observation.keys())
    
    if len(valid_columns - keys) > 0: 
        missing = valid_columns - keys
        error = "Missing columns: {}".format(missing)
        return False, error
    
    if len(keys - valid_columns) > 0: 
        extra = keys - valid_columns
        error = "Unrecognized columns provided: {}".format(extra)
        return False, error    

    return True, ""


def check_categorical_values(observation):
        
    valid_category_map = {
        "sex": ['Male', 'Female'],
        "race" : ['White', 'Black', 'Asian-Pac-Islander', 'Amer-Indian-Eskimo', 'Other'],
        "workclass" : ['State-gov', 'Self-emp-not-inc', 'Private', 'Federal-gov', 'Local-gov', '?', 'Self-emp-inc', 'Without-pay', 'Never-worked'],
        "education" : ['Bachelors', 'HS-grad', '11th', 'Masters', '9th', 'Some-college', 'Assoc-acdm', 'Assoc-voc', '7th-8th', 'Doctorate', 'Prof-school', '5th-6th', '10th', '1st-4th', 'Preschool', '12th'],
        "marital-status" : ['Never-married', 'Married-civ-spouse', 'Divorced', 'Married-spouse-absent', 'Separated', 'Married-AF-spouse', 'Widowed']
    }
    
    for key, valid_categories in valid_category_map.items():
        if key in observation:
            value = observation[key]
            if value not in valid_categories:
                error = "Invalid value provided for {}: {}. Allowed values are: {}".format(
                    key, value, ",".join(["'{}'".format(v) for v in valid_categories]))
                return False, error
        else:
            error = "Categorical field {} missing"
            return False, error
    
    return True, ""


def check_hour(observation):
    
    hours_per_week = observation.get("hours-per-week")
    
    if not hours_per_week:
        error = "Field `hour` missing"
        return False, error

    if not isinstance(hours_per_week, int):
        error = "Field `hour` is not an integer"
        return False, error
    
    if hours_per_week < 0 or hours_per_week > 168:
        error = "Field `hours-per-week` "+ str(hours_per_week) +" is not between 0 and 168"
        return False, error

    return True, ""


def check_age(observation):
    
    age = observation.get('age')
    
    if not age: 
        error = "Field `age` missing"
        return False, error
    
    if not isinstance(age, int):
        error = "Field `age` is not an integer"
        return False, error
    
    if age < 10 or age > 100:
        error = "Field `age` "+ str(age) +" is not between 10 and 100"
        return False, error
    
    return True, ""


# End input validation functions
########################################

########################################
# Begin webserver stuff

app = Flask(__name__)


@app.route('/predict', methods=['POST'])
def predict():
    obs_dict = request.get_json()
  
    request_ok, error = check_request(obs_dict)
    if not request_ok:
        response = {'error': error}
        return jsonify(response)

    _id = obs_dict['observation_id']
    observation = obs_dict['data']

    columns_ok, error = check_valid_column(observation)
    if not columns_ok:
        response = {'error': error}
        return jsonify(response)

    categories_ok, error = check_categorical_values(observation)
    if not categories_ok:
        response = {'error': error}
        return jsonify(response)

    hour_ok, error = check_hour(observation)
    if not hour_ok:
        response = {'error': error}
        return jsonify(response)

    age_ok, error = check_age(observation)
    if not age_ok:
        response = {'error': error}
        return jsonify(response)

    obs = pd.DataFrame([observation], columns=columns).astype(dtypes)
    proba = pipeline.predict_proba(obs)[0, 0]
    prediction = pipeline.predict(obs)[0]
    response = {"observation_id" : _id, "prediction": bool(prediction), "probability": proba }
    p = Prediction(
        observation_id=_id,
        proba=proba,
        observation=request.data,
    )
    try:
        p.save()
    except IntegrityError:
        error_msg = "ERROR: Observation ID: '{}' already exists".format(_id)
        response["error"] = error_msg
        print(error_msg)
        DB.rollback()
    return jsonify(response)

    
@app.route('/update', methods=['POST'])
def update():
    obs = request.get_json()
    try:
        p = Prediction.get(Prediction.observation_id == obs['_id'])
        p.true_class = obs['true_class']
        p.save()
        return jsonify(model_to_dict(p))
    except Prediction.DoesNotExist:
        error_msg = 'Observation ID: "{}" does not exist'.format(obs['_id'])
        return jsonify({'error': error_msg})


    
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000)) # Use port specified by environment variable, or default to 5000
    app.run(host='0.0.0.0', port=port)