import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import urllib2
import datetime
import re
import os
import time
import simplejson as json
import resource
import mysql.connector

mysql_host = os.getenv('JAWSDB_HOST')
mysql_username = os.getenv('JAWSDB_USERNAME')
mysql_password = os.getenv('JAWSDB_PASSWORD')
mysql_database = os.getenv('JAWSDB_DATABASE')

###############################################################################################################################################
########################################################## Define all the functions ###########################################################

def getCurrentAvailability(time_input):
    ## Returns a dict of bike and dock availability where the keys are station ids and the values are dicts like {'b': 123, 'd': 123}
    print("Getting availability data for " + str(time_input.strftime('%Y-%m-%d %H:%M')) + '...')
    bikes_count = 0
    while True:
        try:
            url_xml = urllib2.urlopen('https://www.capitalbikeshare.com/data/stations/bikeStations.xml').read()
            root = ET.fromstring(url_xml)

            terminalName = []
            nbBikes = []
            nbEmptyDocks = []
            lats = []
            lngs = []
            names = []

            for station in root.findall('station'):
                terminalName.append(station.find('terminalName').text)
                nbBikes.append(station.find('nbBikes').text)
                nbEmptyDocks.append(station.find('nbEmptyDocks').text)
                lats.append(station.find('lat').text)
                lngs.append(station.find('long').text)
                names.append(station.find('name').text)

            ## Make the bikes data into a pandas df
            stations = pd.DataFrame(terminalName)
            stations.columns = ['terminalName']
            stations['b'] = pd.Series(nbBikes, index=stations.index)
            stations.set_index('terminalName', drop = True, inplace = True)
            stations.index = stations.index.astype(str)
            stations = stations.astype(int)
            stations_dict = stations['b'].to_dict()

            ## Make an dataframe of station locations
            station_locs = pd.DataFrame(terminalName)
            station_locs.columns = ['terminalName']
            station_locs['lat'] = pd.Series(lats, index=station_locs.index)
            station_locs['lng'] = pd.Series(lngs, index=station_locs.index)
            station_locs['name'] = pd.Series(names, index=station_locs.index)
            station_locs['bikes'] = pd.Series(nbBikes, index=station_locs.index).astype(int)
            station_locs['docks'] = pd.Series(nbEmptyDocks, index=station_locs.index).astype(int)
            station_locs['capacity'] = station_locs.bikes + station_locs.docks
            station_locs.drop(['bikes', 'docks'], axis = 1, inplace = True)
            station_locs.set_index('terminalName', drop = True, inplace = True)
            station_locs.index = station_locs.index.astype(str)
            station_locs['name'] = station_locs.name.astype(str)
            station_locs['capacity'] = station_locs.capacity
            station_locs[['lat','lng']] = station_locs[['lat','lng']].astype(float)
            station_locs = dict(eval(station_locs.to_json(orient = 'index')))

            print("Got station locations data!")

        except Exception as e:
            print("Warning: CaBi availability data retrieval failed. Retrying...")
            print e
            time.sleep(1)
            bikes_count += 1
            if bikes_count == 5:
                print("ERROR: CABI AVAILABILITY DATA RETRIEVAL FATALLY FAILED!!!!!")
                break
            continue
        break
    return stations_dict, station_locs
        
def doTimePoint():
    ###################### Set up the current and previous script start times ######################

    ## Get current time
    init_time = datetime.datetime.now()
    ## Set time interval in minutes
    time_interval = 10
    ## Round time to nearest interval
    discard = datetime.timedelta(minutes = init_time.minute % time_interval, seconds = init_time.second)
    init_time -= discard
    if discard >= datetime.timedelta(minutes = time_interval*0.7):
        init_time += datetime.timedelta(minutes = time_interval)

    ## Get previous time point
    prev_time_point_time = (init_time - datetime.timedelta(minutes = time_interval))

    print("Doing update for time point " + str(init_time.strftime('%Y-%m-%d %H:%M')))

    ######################################## Get the data ########################################

    ## Set the time for the datetime key in the mongodb entry
    date_time = init_time.strftime('%Y-%m-%d %H:%M')

    ## Get the current bike and dock availability for the station_availability key in the mongodb entry
    station_availability, station_locations = getCurrentAvailability(init_time)

    ## Make entry to push to mysql
    entry = {'datetime': date_time, 'station_availability': station_availability, 'station_locations': station_locations}
    
    return entry
        
###############################################################################################################################################

#print "#####################################################################"
print('Initial memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

start_time = datetime.datetime.now()
print start_time

## Get data
entry = doTimePoint()
## Open a connection to the database
mysqldb = mysql.connector.connect(host=mysql_host, user=mysql_username, passwd=mysql_password, db=mysql_database)
cur = mysqldb.cursor()
time_interval = 10
prev_time_point_time = pd.to_datetime(entry['datetime']) - datetime.timedelta(minutes = time_interval)

##################### STATION LOCATIONS PART ###########################
## Create the station_locations table
stat_locs = entry['station_locations']

try:
    create_table_string = "CREATE TABLE station_locations (station FLOAT (5) NOT NULL, lat FLOAT (8), lng FLOAT (8), name VARCHAR (70), capacity INT (3), PRIMARY KEY (station));"
    cur.execute(create_table_string)
    print('Created station_locations table.')
except:
    print('station_locations table already exists.')

print('Updating station_locations table...')
## See what has changed in the station locations table and only update the changes
cur.execute("SELECT * FROM station_locations;")
stat_locs_dict = {}
for ent in cur.fetchall():
    stat = str(int(ent[0]))
    temp_dict_stats_locs = stat_locs.get(stat, 0)
    temp_dict_entry = {'lat': float(ent[1]), 'lng': float(ent[2]), 'capacity': int(ent[4]), 'name': str(ent[3])}
    if type(temp_dict_stats_locs) == int:
        stat_locs_dict[stat] = temp_dict_entry
    else:
        for key in temp_dict_entry.keys():
            if key == 'lat' or key == 'lng':
                temp_dict_entry_ent = float("{0:.4f}".format(round(float(temp_dict_entry[key]), 4)))
                temp_dict_stats_locs_ent = float("{0:.4f}".format(round(float(temp_dict_stats_locs[key]), 4)))
                if np.abs(temp_dict_entry_ent - temp_dict_stats_locs_ent) < 0.0002:
                    temp_dict_entry_ent = temp_dict_stats_locs_ent
            elif key == 'capacity':
                temp_dict_entry_ent = int(temp_dict_entry[key])
                temp_dict_stats_locs_ent = int(temp_dict_stats_locs[key])
            else:
                temp_dict_entry_ent = temp_dict_entry[key]
                temp_dict_stats_locs_ent = re.sub(r'\\','', temp_dict_stats_locs[key])
            if temp_dict_entry_ent != temp_dict_stats_locs_ent:
                temp_dict_entry[key] = temp_dict_stats_locs_ent
                stat_locs_dict[stat] = temp_dict_entry

# print(stat_locs_dict)

try:
    stat_locs_dict_keys = sorted(stat_locs_dict.keys())
except:
    stat_locs_dict_keys = []

if len(stat_locs_dict_keys) > 0:
    for stat in stat_locs_dict_keys:
        try:
            cur.execute("INSERT INTO station_locations (station) VALUES ("+str(stat)+");")
        except:
            blarghbleh = 1
        cur.execute("UPDATE station_locations SET lat = "+str(stat_locs_dict[stat]['lat'])+" WHERE station = "+str(stat)+";")
        cur.execute("UPDATE station_locations SET lng = "+str(stat_locs_dict[stat]['lng'])+" WHERE station = "+str(stat)+";")
        cur.execute('UPDATE station_locations SET name = "'+str(stat_locs_dict[stat]['name'])+'" WHERE station = '+str(stat)+';')
        cur.execute('UPDATE station_locations SET capacity = '+str(stat_locs_dict[stat]['capacity'])+' WHERE station = '+str(stat)+';')
mysqldb.commit()

##################### STATION AVAILABILITY PART ###########################
## Create the station_availability table
stat_avail = entry['station_availability']
stat_avail_keys = sorted(stat_avail.keys())
## Create table if it doesn't already exist
try:
    create_table_string = "CREATE TABLE station_availability (timepoint VARCHAR (20) NOT NULL"
    for each in stat_avail_keys:
        create_table_string += ", `"+str(each)+"` INT"
    create_table_string += ", PRIMARY KEY (timepoint));"
    cur.execute(create_table_string)
    print('Created station_availability table.')
except:
    blarghbleh = 1

print('Updating station_availability table...')
## Get a list of timepoints from table
cur.execute("SELECT timepoint FROM station_availability;")
result = cur.fetchall()
## Make a cutoff time point (2 days is about the most I can have without going over the free space limit in JawsDB mysql)
cutoff_time_point = pd.to_datetime(entry['datetime']) - datetime.timedelta(days = 9)
## Make a list of timepoints to remove from before the cutoff time point
all_timepoints = []
timepoints_to_remove = []
for each in result:
    if pd.to_datetime(each[0]) < cutoff_time_point:
        timepoints_to_remove.append(each[0])
    else:
        all_timepoints.append(pd.to_datetime(each[0]))

## Remove time points before the cutoff time point
if len(timepoints_to_remove) > 0:
    delete_timepoint_string = "DELETE FROM station_availability WHERE timepoint IN ('"+str(timepoints_to_remove[0])+"'"
    for each in timepoints_to_remove[1:]:
        delete_timepoint_string += ", '"+str(each)+"'"
    delete_timepoint_string += ");"
    cur.execute(delete_timepoint_string)

## See if there are any missing time points
if len(all_timepoints) > 0:
    time_range = pd.date_range(start = all_timepoints[0], end = all_timepoints[-1], freq = '10min')
    missing_time_points = sorted(list(set(time_range).symmetric_difference(all_timepoints)))
    ## Go through missing time points and forward fill values
    for timepoint in missing_time_points:
        curr_timepoint = timepoint.strftime('%Y-%m-%d %H:%M')
        prev_timepoint = (timepoint - datetime.timedelta(minutes = 10)).strftime('%Y-%m-%d %H:%M')
        ## Make a temporary table to harbor the data to be forward filled
        update_string_1 = "CREATE TEMPORARY TABLE tmp SELECT * FROM station_availability WHERE timepoint = '"+str(prev_timepoint)+"';"
        cur.execute(update_string_1)
        ## Rename the timepoint in the temporary table to the missing timepoint
        update_string_2 = "UPDATE tmp SET timepoint = '"+str(curr_timepoint)+"' WHERE timepoint = '"+str(prev_timepoint)+"';"
        cur.execute(update_string_2)
        ## Insert the data in the temp table into station_availability
        update_string_3 = "INSERT INTO station_availability SELECT * FROM tmp WHERE timepoint = '"+str(curr_timepoint)+"';"
        cur.execute(update_string_3)
        ## Drop the temporary table
        cur.execute("DROP TABLE tmp;")

## Get station names from table
cur.execute("SHOW COLUMNS FROM station_availability;")
current_stations = []
for each in cur.fetchall():
    if each[0] == 'timepoint':
        continue
    else:
        current_stations.append(str(each[0]))
## Make a list of new stations
new_stations = sorted(list(set(stat_avail_keys)-set(current_stations)))
## Add each new station to the table
if len(new_stations) > 0:
    sql_string = "ALTER TABLE station_availability ADD COLUMN `"+str(new_stations[0])+"` INT"
    for stat in new_stations[1:]:
        sql_string += ", ADD COLUMN `"+str(stat)+"` INT"
    sql_string += ";"
    cur.execute(sql_string)

## Insert new timepoint data into table
sql_string_1 = "INSERT INTO station_availability (timepoint"
sql_string_2 = "VALUES ('"+str(entry['datetime'])+"'"
for stat in stat_avail_keys:
    sql_string_1 += ", `"+str(stat)+"`"
    sql_string_2 += ", "+str(stat_avail[stat])

sql_string_1 += ") "
sql_string_2 += ");"
try:
    cur.execute(sql_string_1+sql_string_2)
except:
    print('Time point already in database.')

## Commit the updates to the database and close the connection
mysqldb.commit()

get_size_string = 'SELECT table_schema "DB Name", Round(Sum(data_length + index_length) / 1024 / 1024, 1) "DB Size in MB" FROM information_schema.tables GROUP BY table_schema;'
cur.execute(get_size_string)
res = cur.fetchall()
for each in res:
    print('Database size is '+str(res[0][1])+' MB.')
    break
try:
    print('Number of entries is '+str(len(time_range)))+'.'
    print('Size per entry is rougly '+str(res[0][1]/len(time_range)))+'.'
except:
    print 'This was the first entry!'

mysqldb.close()

print('Final memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
print('Script took ' + str(datetime.datetime.now() - start_time))
