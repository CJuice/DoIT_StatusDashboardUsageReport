# Export total number of requests for all services in a site
# ArcGIS Server 10.3 or higher

# For HTTP calls
import httplib
import urllib
import urllib2
import json
# For time-based functions
import time
import uuid
import datetime
import calendar
# For system tools
import sys
import os
# For reading passwords without echoing
import getpass
# For writing csv files
import csv
import configparser


# Defines the entry point into the script
def main():

    # VARIABLES
    _ROOT_PROJECT_PATH = os.path.dirname(__file__)
    CREDENTIALS_PATH = os.path.join(_ROOT_PROJECT_PATH, "Docs/credentials.cfg")
    config = configparser.ConfigParser()
    config.read(fileName=CREDENTIALS_PATH)

    CSV_OUTPUT_FILE_PATH = r"D:\inetpub\wwwroot\DOIT\StatusDashboard\temp\UsageStatistics.csv"
    PASSWORD = config["ags_server_credentials"]["password"]
    SERVER_MACHINE_NAMES = {0: config['ags_prod_machine_names']["machine1"],
                            1: config['ags_prod_machine_names']["machine2"],
                            2: config['ags_prod_machine_names']["machine3"],
                            3: config['ags_prod_machine_names']["machine4"]}
    SERVER_PORT_SECURE = config['ags_prod_machine_names']["secureport"]
    SERVER_ROOT_URL = "https://{machine_name}.mdgov.maryland.gov:{port}"
    SERVER_URL_ADMIN_SERVICES = "arcgis/admin/services"
    SERVER_URL_GENERATE_TOKEN = "arcgis/admin/generateToken"
    USERNAME = config["ags_server_credentials"]["username"]

    # Ask for server name
    serverName = "geodata.md.gov"
    serverPort = 443

    # CLASSES

    # FUNCTIONS

    # FUNCTIONALITY

    # Get a token
    token = getToken(USERNAME, PASSWORD, serverName, serverPort)
    if token == "":
        print("Could not generate a token with the user name and password provided.")
        return
    
    # Get list of all services in all folders on sites
    services = getServiceList(serverName, serverPort, token)
    
    # Construct URL to query the logs
    statsCreateReportURL = "https://" + serverName + "/imap/admin/usagereports/add".format(serverName, serverPort)

    # Create unique name for temp report
    reportName = uuid.uuid4().hex
    
  
    nowtime = datetime.datetime.utcnow()
    toTime = dt2ts(nowtime) *1000
    fromTime = dt2ts(nowtime - datetime.timedelta(hours=48)) *1000
    print(int(toTime))
    print(int(fromTime))
    
    # Create report JSON definition
    statsDefinition = { 'reportname' : reportName,
           'since' : 'CUSTOM',
           'from': int(fromTime),
           'to': int(toTime),
           'queries' : [{ 'resourceURIs' : services,
           'metrics' : ['RequestCount'] }],
           'aggregationInterval' : 60,                        
           'metadata' : { 'temp' : True,
           'tempTimer' : 1454109613248 } }

    postdata = { 'usagereport' : json.dumps(statsDefinition) }
    createReportResult = postAndLoadJSON(statsCreateReportURL, token, postdata)

    # Query newly created report
    statsQueryReportURL = "https://" + serverName + "/imap/admin/usagereports/{2}/data".format(serverName, serverPort, reportName)
    postdata = { 'filter' : { 'machines' : '*'} }
    postAndLoadCSV(statsQueryReportURL, CSV_OUTPUT_FILE_PATH, token, postdata)
    
    print("Before delete")
    # Cleanup (delete) statistics report
    statsDeleteReportURL = "https://" + serverName + "/imap/admin/usagereports/{2}/delete".format(serverName, serverPort, reportName)
    deleteReportResult = postAndLoadJSON(statsDeleteReportURL, token)
    
    print("Export complete!")

    return


def dt2ts(dt):
    return calendar.timegm(dt.utctimetuple())  

# A function that makes an HTTP POST request and returns the result JSON object
def postAndLoadCSV(url, fileName, token = None, postdata = None):
    if not postdata: postdata = {}
    # Add token to POST data if not already present and supplied
    if token and 'token' not in postdata: postdata['token'] = token 
    # Add JSON format specifier to POST data if not already present
    if 'f' not in postdata: postdata['f'] = 'csv'
    
    # Encode data and POST to server
    postdata = urllib.urlencode(postdata)
    response = urllib2.urlopen(url, data = postdata)

    print('post data')
    if (response.getcode() != 200):
        response.close()
        raise Exception('Error performing request to {0}'.format(url))

    csvreader = csv.reader(response)
    # Open output file
    output = open(fileName, 'wb')
    csvwriter = csv.writer(output, dialect='excel')
    csvwriter.writerows(csvreader)
    output.close()  
    response.close()
    
    # Deserialize response into Python object
    return 

# A function that makes an HTTP POST request and returns the result JSON object
def postAndLoadJSON(url, token = None, postdata = None):
    if not postdata: postdata = {}
    # Add token to POST data if not already present and supplied
    if token and 'token' not in postdata: postdata['token'] = token 
    # Add JSON format specifier to POST data if not already present
    if 'f' not in postdata: postdata['f'] = 'json'
    
    # Encode data and POST to server
    postdata = urllib.urlencode(postdata)
    response = urllib2.urlopen(url, data=postdata)

    print('post data')
    if (response.getcode() != 200):
        response.close()
        raise Exception('Error performing request to {0}'.format(url))

    data = response.read()
    response.close()

    print('postandloadjson')
    # Check that data returned is not an error object
    if not assertJsonSuccess(data):          
        raise Exception("Error returned by operation. " + data)

    # Deserialize response into Python object
    return json.loads(data)

# A function that enumerates all services in all folders on site
def getServiceList(serverName, serverPort, token):
    rooturl = "https://" + serverName + "/imap/admin/services".format(serverName, serverPort)

    root = postAndLoadJSON(rooturl, token)

    services = [] 
	# dont include the services at the root of the server
    #for service in root['services']:
    #    services.append("services/{0}.{1}".format(service['serviceName'], service['type']))

    folders = root['folders']
    for folderName in folders:
        if (folderName != "System" and folderName != "Utilities" and folderName != "GeoprocessingServices"):
            services.append("services/" + folderName)
            folderurl = "{0}/{1}".format(rooturl, folderName)
            folder = postAndLoadJSON(folderurl, token)
            for service in folder['services']:
                services.append("services/{0}/{1}.{2}".format(folderName, service['serviceName'], service['type']))
        
    return services
    
#A function to generate a token given username, password and the adminURL.
def getToken(username, password, serverName, serverPort):
    # Token URL is typically https://server[:port]/arcgis/admin/generateToken
    tokenURL = "/imap/admin/generateToken"

    # URL-encode the token parameters
    params = urllib.urlencode({'username': username, 'password': password, 'client': 'requestip', 'f': 'json'})
    
    headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
    
    # Connect to URL and post parameters
    httpsConn = httplib.HTTPSConnection(serverName, serverPort)
    httpsConn.request("POST", tokenURL, params, headers)

    # Read response
    response = httpsConn.getresponse()
    print(response.read())
    if (response.status != 200):
        httpsConn.close()
        print("Error while fetching tokens from the admin URL. Please check the URL and try again.")
        return
    else:
        data = response.read()
        httpsConn.close()

        # Check that data returned is not an error object
        if not assertJsonSuccess(data): 
            return
        
        # Extract the token from it
        token = json.loads(data)       
        return token['token']            

#A function that checks that the input JSON object
#  is not an error object.    
def assertJsonSuccess(data):
    obj = json.loads(data)
    if 'status' in obj and obj['status'] == "error":
        print("Error: JSON object returns an error. " + str(obj))
        return False
    else:
        return True
    
        
# Script start
if __name__ == "__main__":
    main()
