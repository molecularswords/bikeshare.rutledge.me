from flask import Flask, render_template, redirect, url_for,request
from flask import make_response
from sklearn.linear_model import LinearRegression
import numpy as np
import pandas as pd
import datetime
import mysql.connector
import os
import pytz
import simplejson as json

## Get mysql credentials
mysql_host = os.getenv('JAWSDB_HOST')
mysql_username = os.getenv('JAWSDB_USERNAME')
mysql_password = os.getenv('JAWSDB_PASSWORD')
mysql_database = os.getenv('JAWSDB_DATABASE')

app = Flask(__name__, static_url_path='')

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/')
def dots_ping():
    return app.send_static_file('animated_rides.html')

@app.route('/')
def dots_heatmap():
    return app.send_static_file('animated_availability_heatmap.html')

@app.route('/')
def weekday_clusters():
    return app.send_static_file('weekday_clusters.html')

@app.route('/')
def weekend_clusters():
    return app.send_static_file('weekend_clusters.html')



@app.route('/station_locations', methods=['GET', 'POST'])
def station_locations():
    message = None
    if request.method == 'POST':
        def get_station_locations():

            ## Open database connection
            mysqldb = mysql.connector.connect(host=mysql_host, user=mysql_username, passwd=mysql_password, db=mysql_database)
            cur = mysqldb.cursor()

            ## Get station names
            field_names = []
            cur.execute("SELECT `COLUMN_NAME` FROM `INFORMATION_SCHEMA`.`COLUMNS` WHERE `TABLE_SCHEMA`='afj8pdq6oui1ik8d' AND `TABLE_NAME`='station_locations';")
            for entry in cur.fetchall():
                field_names.append(entry[0])

            ## Field names will be ['station','lat','lng','name']

            cur.execute("SELECT * FROM station_locations;")
            stations = []
            lats = []
            lngs = []
            names = []
            capacities = []
            for each in cur.fetchall():
                stations.append(int(each[0]))
                lats.append(each[1])
                lngs.append(each[2])
                names.append(each[3])
                capacities.append(each[4])

            stat_locs = {}
            for i in range(len(stations)):
                stat_locs[stations[i]] = {'lat': lats[i], 'lng': lngs[i], 'name': names[i], 'capacity': capacities[i]}

            return stat_locs

        ## Get submitted data from the #submitbutton result in the html file
        data_from_js = request.form['mydata_stat_locs'].split('|||')
        ## Get station locations
        stat_locs = get_station_locations()
        ## Return the response
        resp = make_response(json.dumps(stat_locs))
        resp.headers['Content-Type'] = "application/json"
        return resp
        return render_template('station_locations.html', message='')

@app.route('/prediction', methods=['GET', 'POST'])
def prediction():
    message = None
    if request.method == 'POST':
        def predict_bikes(station, time_to_predict):
            ## Open database connection
            mysqldb = mysql.connector.connect(host=mysql_host, user=mysql_username, passwd=mysql_password, db=mysql_database)
            cur = mysqldb.cursor()

            actual_value = 'future_time'
            
            cur.execute("SELECT `"+str(station)+"` FROM station_availability WHERE timepoint = '"+str(time_to_predict)+"';")
            for each in cur.fetchall():
                actual_value = int(each[0])
                break

            ## Check how far away time to predict is from current time
            tz = pytz.timezone('America/New_York')
            current_datetime = datetime.datetime.now(tz)
            current_datetime -= datetime.timedelta(minutes = current_datetime.minute % 10)
            current_datetime = pd.to_datetime(current_datetime.strftime('%Y-%m-%d %H:%M'))
            ## Convert time_to_predict into datetime
            datetime_to_predict = pd.to_datetime(time_to_predict)
            if current_datetime != datetime_to_predict:
                time_difference = (datetime_to_predict - current_datetime).seconds / 60
            else:
                time_difference = 0

            if actual_value == 'future_time' and time_difference == 0:
                print("Database hasn't updated yet!")
                datetime_to_predict -= datetime.timedelta(minutes = 10)
            ## Set the datetime that will be used for the test_X prediction
            datetime_for_data = datetime_to_predict - datetime.timedelta(minutes = time_difference)
            
            ## Get data for training the model
            ## Make date range to get values for the day 1 week prior to the query
            ############## USE THIS FOR TESTING UNTIL ENOUGH DATA ARE ACQUIRED, THEN CHANGE FROM 1 DAY TO 7 DAYS PRIOR ####################
            start_time = datetime_to_predict - datetime.timedelta(hours = 24)
            end_time = datetime_to_predict - datetime.timedelta(minutes = 20)

            ## Make container for data
            train_Xs = []
            train_ys = []
            ## Make function to get data from database
            def getDataBetweenTimes(cursor, station_of_interest, time_start, time_end):
                ## This function connects to the database passed in by the cursor argument.
                ## It gets data from the database for a passed in station between two times passed in as datetime objects.
                timepoints_list = []
                temp_list = []
                ## Get all the training values
                cursor.execute("SELECT timepoint, `"+str(station_of_interest)+"` FROM station_availability WHERE timepoint BETWEEN '"+
                            str(time_start.strftime('%Y-%m-%d %H:%M'))+"' and '"+
                            str(time_end.strftime('%Y-%m-%d %H:%M'))+"';")
                for temp_entry in cursor.fetchall():
                    timepoints_list.append(temp_entry[0])
                    temp_list.append(int(temp_entry[1]))
                return timepoints_list, temp_list
            ## Define a function to make lag features
            def makeTrainingLags(index_list, values_list, number_of_lags):
                ## Make a dataframe of the values and timepoints
                temp_df = pd.DataFrame(values_list, index = index_list, columns = ['y'])
                ## Add lags
                for i in range(1,number_of_lags+1):
                    temp_df['lag_'+str(10*i+time_difference)] = temp_df.y.shift(i+time_difference/10)
                ## Drop NAs
                temp_df.dropna(inplace = True, axis = 0)
                ## Return X and y values
                return temp_df.drop('y', axis = 1), temp_df.y

            ## Get training data
            train_timepoints_list, train_values_list = getDataBetweenTimes(cur, station, start_time, end_time)
            train_Xs, train_ys = makeTrainingLags(train_timepoints_list, train_values_list, 6)
            
            ## Get data for making the prediction
            test_start_time = datetime_for_data - datetime.timedelta(minutes = 60)
            test_end_time = datetime_for_data - datetime.timedelta(minutes = 10)
            test_timepoints_list, test_X = getDataBetweenTimes(cur, station, test_start_time, test_end_time)

            lr = LinearRegression()
            lr.fit(train_Xs, train_ys)
            prediction = int(round(lr.predict(np.array(test_X).reshape(1,-1))))
            
            return prediction, actual_value

        ## Get submitted data from the #submitbutton result in the html file
        data_from_js = request.form['mydata'].split('___')
        time_to_predict = data_from_js[0]
        station = data_from_js[1]
        start_or_end = data_from_js[2]
        ## Make the prediction
        pred, actual_value = predict_bikes(station, time_to_predict)
        ## Return the response
        resp = make_response(json.dumps({'prediction': str(pred), 'station': str(station), 'start_or_end': str(start_or_end)}))
        resp.headers['Content-Type'] = "application/json"
        return resp
        return render_template('prediction.html', message='')

@app.route('/dots_ping', methods=['GET', 'POST'])
def dots_ping_data():
    message = None
    if request.method == 'POST':
        def get_rides(time_to_predict):
            ## Open database connection
            mysqldb = mysql.connector.connect(host=mysql_host, user=mysql_username, passwd=mysql_password, db=mysql_database)
            cur = mysqldb.cursor()
            ## Get station names
            station_names = []
            cur.execute("SELECT `COLUMN_NAME` FROM `INFORMATION_SCHEMA`.`COLUMNS` WHERE `TABLE_SCHEMA`='afj8pdq6oui1ik8d' AND `TABLE_NAME`='station_availability';")
            for entry in cur.fetchall():
                if entry[0] != 'timepoint':
                    station_names.append(str(entry[0]))
            ## Convert time_to_predict to datetime
            time_start = pd.to_datetime(str(time_to_predict)+' 02:50')
            time_end = pd.to_datetime(str(time_to_predict)+' 23:50') + datetime.timedelta(minutes = 10, hours = 3)
            ## Get data for given day
            cur.execute("SELECT * FROM station_availability WHERE timepoint BETWEEN '"+
                        str(time_start.strftime('%Y-%m-%d %H:%M'))+"' and '"+
                        str(time_end.strftime('%Y-%m-%d %H:%M'))+"';")
            timepoints = []
            values = []
            for each in cur.fetchall():
                timepoints.append(each[0])
                values.append(each[1:])

            df = pd.DataFrame(values, index = timepoints, columns = station_names)
            rides_df = (df - df.shift(1)).dropna(axis = 0).astype(int)
            rides = {}
            for ind in rides_df.index:
                ## Get all departures and arrivals at this timepoint
                deps = rides_df.loc[ind].loc[rides_df.loc[ind] < 0]
                arrs = rides_df.loc[ind].loc[rides_df.loc[ind] > 0]
                ## Make a list of length of deps with random ints between 0 and 9 (inclusive)
                dep_mins = np.random.randint(0,2,deps.shape[0])*5
                dep_inds = deps.index.tolist()
                ## Assign each entry in the current timepoint to a minute in between the current timepoint and the next one
                for temp_ind in range(deps.shape[0]):
                    temp_time = ind[:-1]+str(dep_mins[temp_ind])
                    if rides.get(temp_time, 'NOPE') == 'NOPE':
                        rides[temp_time] = {'dep': {dep_inds[temp_ind]: deps.iloc[temp_ind]}, 'arr': {}}
                    else:
                        rides[temp_time]['dep'][dep_inds[temp_ind]] = deps.iloc[temp_ind]
                ## Make a list of length of arrs with random ints between 0 and 9 (inclusive)
                arr_mins = np.random.randint(0,2,arrs.shape[0])*5
                arr_inds = arrs.index.tolist()
                ## Assign each entry in the current timepoint to a minute in between the current timepoint and the next one
                for temp_ind in range(arrs.shape[0]):
                    temp_time = ind[:-1]+str(arr_mins[temp_ind])
                    if rides.get(temp_time, 'NOPE') == 'NOPE':
                        rides[temp_time] = {'arr': {arr_inds[temp_ind]: arrs.iloc[temp_ind]}}
                    else:
                        rides[temp_time]['arr'][arr_inds[temp_ind]] = arrs.iloc[temp_ind]
            
            return rides

        ## Get submitted data from the #submitbutton result in the html file
        time_to_predict = request.form['mydata']
        ## Make the prediction
        pred = get_rides(time_to_predict)
        ## Return the response
        resp = make_response(json.dumps(pred))
        resp.headers['Content-Type'] = "application/json"
        return resp
        return render_template('prediction.html', message='')

@app.route('/dots_heatmap', methods=['GET', 'POST'])
def dots_heatmap_data():
    message = None
    if request.method == 'POST':
        def get_bikes(time_to_predict):
            ## Open database connection
            mysqldb = mysql.connector.connect(host=mysql_host, user=mysql_username, passwd=mysql_password, db=mysql_database)
            cur = mysqldb.cursor()
            ## Get station names
            station_names = []
            cur.execute("SELECT `COLUMN_NAME` FROM `INFORMATION_SCHEMA`.`COLUMNS` WHERE `TABLE_SCHEMA`='afj8pdq6oui1ik8d' AND `TABLE_NAME`='station_availability';")
            for entry in cur.fetchall():
                if entry[0] != 'timepoint':
                    station_names.append(str(entry[0]))
            ## Convert time_to_predict to datetime
            time_start = pd.to_datetime(str(time_to_predict)+' 02:50')
            time_end = pd.to_datetime(str(time_to_predict)+' 23:50') + datetime.timedelta(minutes = 10, hours = 3)
            ## Get data for given day
            cur.execute("SELECT * FROM station_availability WHERE timepoint BETWEEN '"+
                        str(time_start.strftime('%Y-%m-%d %H:%M'))+"' and '"+
                        str(time_end.strftime('%Y-%m-%d %H:%M'))+"';")
            timepoints = []
            values = []
            for each in cur.fetchall():
                timepoints.append(each[0])
                values.append(each[1:])

            df = pd.DataFrame(values, index = timepoints, columns = station_names).astype(int)
            
            return df.T.to_dict()

        ## Get submitted data from the #submitbutton result in the html file
        time_to_predict = request.form['mydata']
        ## Make the prediction
        pred = get_bikes(time_to_predict)
        ## Return the response
        resp = make_response(json.dumps(pred))
        resp.headers['Content-Type'] = "application/json"
        return resp
        return render_template('prediction.html', message='')

if __name__ == '__main__':
    app.run(host='0.0.0.0')
