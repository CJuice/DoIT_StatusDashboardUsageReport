"""TODO: Doc strings for entire script"""
# Export total number of requests for all services in a site
# ArcGIS Server 10.3 or higher


def main():
    import calendar
    import configparser
    import datetime
    import json
    import os
    import random
    import requests
    import uuid

    # urllib3 is included in requests but to manage the InsecureRequestWarning it was also imported directly
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning
    # Without disabled warnings, every request would print a red warning. This is because we have chosen
    #   'verify=False' when making requests to secure services.
    urllib3.disable_warnings(InsecureRequestWarning)

    # VARIABLES
    _ROOT_PROJECT_PATH = os.path.dirname(__file__)
    CREDENTIALS_PATH = os.path.join(_ROOT_PROJECT_PATH, "Docs/credentials.cfg")
    config = configparser.ConfigParser()
    config.read(filenames=CREDENTIALS_PATH)

    # CSV_OUTPUT_FILE_PATH = r"D:\inetpub\wwwroot\DOIT\StatusDashboard\temp\UsageStatistics.csv"  # PRODUCTION.
    # *********DOIT folder DNE on imap01d
    CSV_OUTPUT_FILE_PATH = r"D:\scripts\StatusDashboard\UsageReport_MOD_testing\UsageStatistics.csv"    # TESTING

    PASSWORD = config["ags_server_credentials"]["password"]
    SERVER_MACHINE_NAMES = {0: config['ags_prod_machine_names']["machine1"],
                            1: config['ags_prod_machine_names']["machine2"],
                            2: config['ags_prod_machine_names']["machine3"],
                            3: config['ags_prod_machine_names']["machine4"]}
    SERVER_PORT_SECURE = config['ags_prod_machine_names']["secureport"]
    SERVER_ROOT_URL = "https://{machine_name}.mdgov.maryland.gov:{port}"
    USERNAME = config["ags_server_credentials"]["username"]

    # CLASSES
    class AdminObject:
        ADMIN_SERVICES_ENDING = "arcgis/admin/services"
        GEODATA_ROOT = "https://geodata.md.gov/imap/rest/services"
        REST_URL_ENDING = "arcgis/rest/services"
        GENERATE_TOKEN_ENDING = "arcgis/admin/generateToken"

        def __init__(self, root_machine_url):
            self.admin_services_url = root_machine_url
            self.rest_url_machine_root = root_machine_url

        @property
        def admin_services_url(self):
            return self.__admin_services_url

        @admin_services_url.setter
        def admin_services_url(self, value):
            self.__admin_services_url = f"{value}/{AdminObject.ADMIN_SERVICES_ENDING}"

        @property
        def rest_url_machine_root(self):
            return self.__rest_url_machine_root

        @rest_url_machine_root.setter
        def rest_url_machine_root(self, value):
            self.__rest_url_machine_root = f"{value}/{AdminObject.REST_URL_ENDING}"

    class FolderObject(AdminObject):
        """
        Example: 'https://gis-ags-imap02p.mdgov.maryland.gov:6443/arcgis/rest/services/Weather'
        FOLDER_URL_ENDING = "{folder}"
        """

        def __init__(self, name, root_machine_url):
            super().__init__(root_machine_url=root_machine_url)     # Needs to be instantiated before folder_url
            self.name = name
            self.folder_machine_url = name
            self.folder_geodata_url = name
            self.services_json = None
            self.service_objects_list = []

        @property
        def folder_geodata_url(self):
            return self.__folder_geodata_url

        @folder_geodata_url.setter
        def folder_geodata_url(self, value):
            self.__folder_geodata_url = f"{AdminObject.GEODATA_ROOT}/{value}"

        @property
        def folder_machine_url(self):
            return self.__folder_machine_url

        @folder_machine_url.setter
        def folder_machine_url(self, value):
            self.__folder_machine_url = f"{self.rest_url_machine_root}/{value}"

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"FOLDER: {self.name}-->\n\turl on machine = {self.folder_machine_url}\n\turl on geodata = {self.folder_geodata_url}"

    class MachineObject:
        """Created to store machine properties and values."""

        def __init__(self, machine_name, root_url, security_token, folder_names=None):
            """
            Instantiate the machine objects
            :param machine_name: name of the server machine
            :param root_url: root url for machine
            :param security_token: the token generated by the machine for secure access
            :param folder_names: list of folders discovered during inspection of the services
            """
            self.machine_name = machine_name
            self.root_url = root_url
            self.token = security_token
            self.folder_names_list = folder_names

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"MACHINE: {self.machine_name}-->\n\troot url = {self.root_url}\n\ttoken = {self.token}\n\t" \
                   f"folders list = {self.folder_names_list}"

    class NotJSONException(Exception):
        """Raised when the url for the request is malformed for our purposes and the server returns html, not json"""
        def __init__(self):
            pass

        def __str__(self):
            return "Content is not in JSON format. CJuice"

    class ReportObject(AdminObject):
        """
        'add' is trigger for report creation
        'data' is trigger for querying
        'delete' is trigger for deleting report
        """
        USAGE_REPORT_ENDING__CREATE = "arcgis/admin/usagereports/add"
        USAGE_REPORT_ENDING__QUERY = "arcgis/admin/usagereports/{report_name}/data"
        USAGE_REPORT_ENDING__DELETE = "arcgis/admin/usagereports/{report_name}/delete"

        def __init__(self, root_machine_url, master_urls_list, basic_request_json):
            super().__init__(root_machine_url)
            self.report_name_id = uuid.uuid4().hex
            self.now_time = datetime.datetime.utcnow()
            self.to_time = ReportObject.dt2ts(self.now_time) * 1000
            self.from_time = ReportObject.dt2ts(self.now_time - datetime.timedelta(hours=48)) * 1000
            self.master_urls_list = master_urls_list
            self.json_definition = None
            self.report_json_params = basic_request_json
            # self.report_query_params = None
            self.usage_reports_url__create = root_machine_url
            self.usage_reports_url__query = root_machine_url
            self.usage_reports_url__delete = root_machine_url
            self.report_url_create = None
            self.report_url_query = None
            self.report_url_delete = None

        @property
        def report_url_create(self):
            return self.__report_url_create

        @report_url_create.setter
        def report_url_create(self, value):
            create_url = self.usage_reports_url__create.format(report_name=self.report_name_id)
            # self.__report_url_delete = self.usage_reports_url__delete.format(report_name=self.report_name_id)
            self.__report_url_create = create_url

        @property
        def report_url_delete(self):
            return self.__report_url_delete

        @report_url_delete.setter
        def report_url_delete(self, value):
            delete_url = self.usage_reports_url__delete.format(report_name=self.report_name_id)
            # self.__report_url_delete = self.usage_reports_url__delete.format(report_name=self.report_name_id)
            self.__report_url_delete = delete_url

        @property
        def report_url_query(self):
            return self.__report_url_query

        @report_url_query.setter
        def report_url_query(self, value):
            query_url = self.usage_reports_url__query.format(report_name=self.report_name_id)
            # self.__report_url_query = self.usage_reports_url__query.format(report_name=self.report_name_id)
            self.__report_url_query = query_url

        @property
        def json_definition(self):
            return self.__json_definition

        @json_definition.setter
        def json_definition(self, value):
            # Create report JSON definition. This json object goes into the json object submitted to the server.
            #   The object details indicate what is to be put into the report when it is built
            #   'resourceURIs' is a list of all service and folder urls per Jessie design
            #   NOTE: When python provides you with a dictionary it does so with single quotes not double quotes as
            #       I have indicated below. Single quotes are not recognized as valid json so json.dumps() must be used
            #       to create a json string with double quotes.
            self.__json_definition = {"reportname": self.report_name_id,
                                      "since": "CUSTOM",
                                      "from": int(self.from_time),
                                      "to": int(self.to_time),
                                      "queries": [
                                          {"resourceURIs": self.master_urls_list,
                                           "metrics": ["RequestCount"]}
                                      ],
                                      "aggregationInterval": 60,
                                      "metadata": {"temp": True,
                                                   "tempTimer": 1454109613248}
                                      }

        @property
        def report_json_params(self):
            return self.__report_json_params

        @report_json_params.setter
        def report_json_params(self, value):
            """
            NOTE: Proved absolutely essential for the usagereport value to be processed by json.dumps(). Received an
            error in response saying 'A JSONObject text must begin with '{' at character 1 of ...'
            :param value:
            :return:
            """
            value.update({"usagereport": json.dumps(self.json_definition)})
            # print(f"Report Json Params: {value}")   # TESTING
            self.__report_json_params = value

        @property
        def usage_reports_url__create(self):
            return self.__usage_reports_url__create

        @usage_reports_url__create.setter
        def usage_reports_url__create(self, value):
            self.__usage_reports_url__create = f"{value}/{ReportObject.USAGE_REPORT_ENDING__CREATE}"

        @property
        def usage_reports_url__delete(self):
            return self.__usage_reports_url__delete

        @usage_reports_url__delete.setter
        def usage_reports_url__delete(self, value):
            self.__usage_reports_url__delete = f"{value}/{ReportObject.USAGE_REPORT_ENDING__DELETE}"

        @property
        def usage_reports_url__query(self):
            return self.__usage_reports_url__query

        @usage_reports_url__query.setter
        def usage_reports_url__query(self, value):
            self.__usage_reports_url__query = f"{value}/{ReportObject.USAGE_REPORT_ENDING__QUERY}"

        @staticmethod
        def dt2ts(date_time_object):
            # Is a function Jessie created.
            return calendar.timegm(date_time_object.utctimetuple())

    class ServiceObject(AdminObject):
        """
        Example: 'https://gis-ags-imap02p.mdgov.maryland.gov:6443/arcgis/rest/services/Weather/MD_StormSurge/MapServer'
        REST_URL_END = "{folder}/{service_name}/{type}
        """

        def __init__(self, folder, service_json, root_machine_url):
            super().__init__(root_machine_url=root_machine_url)
            self.folder = folder
            self.service_name = service_json
            self.service_type = service_json
            self.service_url = None
            self.service_admin_properties_url = None

        @property
        def service_name(self):
            return self.__service_name

        @service_name.setter
        def service_name(self, value):
            try:
                self.__service_name = value['name']
            except KeyError as ke:
                print(f"KeyError: 'name' not found in services json for this service. {ke}")

        @property
        def service_type(self):
            return self.__service_type

        @service_type.setter
        def service_type(self, value):
            try:
                self.__service_type = value['type']
            except KeyError as ke:
                print(f"KeyError: 'type' not found in services json for this service. {ke}")

        @property
        def service_admin_properties_url(self):
            return self.__service_admin_properties_url

        @service_admin_properties_url.setter
        def service_admin_properties_url(self, value):
            self.__service_admin_properties_url = f"{self.admin_services_url}/{self.service_name}.{self.service_type}"

        @property
        def service_url(self):
            return service.__service_url

        @service_url.setter
        def service_url(self, value):
            self.__service_url = f"{self.rest_url_machine_root}/{self.service_name}/{self.service_type}"

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"SERVICE: {self.service_name}-->\n\ttype = {self.service_type}\n\tfolder = {self.folder}"

    # FUNCTIONS
    def create_params_for_request(token_action=None, json_payload=None, response_format="json"):
        """
        Create parameters to be submitted with the request.
        :param token_action: route to be taken when creating the parameters
        :param json_payload:
        :param response_format:
        :return: dictionary of parameters
        """
        if token_action is None and json_payload is None:
            values = {'f': response_format}
        elif token_action == "getToken":
            values = {'username': USERNAME, 'password': PASSWORD, 'client': 'requestip', 'f': response_format}
        elif token_action is not None and json_payload is not None:
            values = {'token': token_action, 'f': response_format}
            values.update(json_payload)
        else:
            values = {'token': token_action, 'f': response_format}
        return values

    def clean_url_slashes(url):
        """
        Standardize the slashes when use of os.path.join() with forward slashes in url's.
        os.path.join() uses back slashes '\' while http uses forward slashes '/'
        :param url: url to be examined
        :return: standardized url string
        """
        url = url.replace("\\", "/")
        return url

    def create_master_url_list(objects_list):
        # need a list of folder url's
        # folder_urls = [obj.folder_machine_url for obj in objects_list]
        master_list = []
        for obj_fold in objects_list:
            master_list.append(obj_fold.folder_machine_url)
            for obj_serv in obj_fold.service_objects_list:
                master_list.append(obj_serv.service_admin_properties_url)
        return master_list

    def create_random_int(upper_integer):
        """
        Create and return a random integer from 0 to one less than the upper range value.
        :param upper_integer: upper integer of range to be used
        :return: integer
        """
        options = upper_integer - 1
        spot = random.randint(0, options)
        return spot

    def get_response(url, params):
        """
        Submit a request with parameters to a url and inspect the response json for the specified key of interest.
        :param url: url to which to make a request
        :param params: parameters to accompany the request
        :return: content of json if key present in response
        """
        # To deal with mixed path characters between url syntax and os.path.join use of "\"
        url = clean_url_slashes(url)

        try:
            # Jessie discovered "verify" option and set to False to bypass the ssl issue
            response = requests.post(url=url, data=params, verify=False)
        except Exception as e:
            print("Error in response from requests: {}".format(e))
            exit()
        else:
            # print(f"RESPONSE URL: {response.url}")
            # print(f"RESPONSE encoding: {response.encoding}")
            # print(f"RESPONSE content type: {type(response.content)}")
            result = None
            try:
                # print(f"RESPONSE HEADERS: {response.headers}")
                if "html" in response.headers["Content-Type"]:
                    raise NotJSONException
                elif "text/csv" in response.headers["Content-Type"]:
                    result = response
                elif "application/json" in response.headers["Content-Type"]:
                    result = response.json()
            except json.decoder.JSONDecodeError as jde:
                print("Error decoding response to json: {}".format(jde))
                print(response)
                print(response.url)
                print(response.text)
                exit()
            except NotJSONException as NJE:
                print(f"Response appears to be html, not json.")
                print(response.url)
                print(response.headers)
                # print(response.text)
                exit()
            return result

    def search_json_for_key(response_json, search_key):
        try:
            value = response_json[search_key]
        except KeyError as ke:
            print("KeyError: {}".format(ke))
            exit()
        except TypeError as te:
            print("TypeError: {}".format(te))
            print(response_json)
            exit()
        else:
            return value

    def write_response_to_csv(response, csv_path):
        with open(csv_path, 'w') as csv_file_handler:
            for line in response.text:
                csv_file_handler.write(line)
        return

    # FUNCTIONALITY
    #   Need a machine to which to make a request. Select at random from 4 total since we are bypassing web adaptor.
    machine = SERVER_MACHINE_NAMES[create_random_int(upper_integer=len(SERVER_MACHINE_NAMES))]

    #   Need a token to make secure requests
    root_server_url = SERVER_ROOT_URL.format(machine_name=machine, port=SERVER_PORT_SECURE)
    generate_token_url = os.path.join(root_server_url, AdminObject.GENERATE_TOKEN_ENDING)
    token_params = create_params_for_request(token_action="getToken")
    token_response = get_response(url=generate_token_url, params=token_params)
    token = search_json_for_key(response_json=token_response, search_key="token")

    #   Create a machine object for the selected ArcGIS Server machine. To store related values in object. Folders
    #       variable assigned below
    machine_object = MachineObject(machine_name=machine,
                                   root_url=root_server_url,
                                   security_token=token)

    #   Need to make a secure request for response as JSON to be able to access folders and services details
    basic_secure_params = create_params_for_request(token_action=machine_object.token)
    admin_object = AdminObject(root_machine_url=root_server_url)
    folders_request_response = get_response(url=admin_object.admin_services_url, params=basic_secure_params)

    #   Need folder names list and to clean list; Remove System & Utilities, & append entry for root folder, per Jessie
    #   NOTE: Noticed that Jessie also included 'GeoprocessingServices', but did not in statusdashboard script
    folder_names_raw = search_json_for_key(response_json=folders_request_response, search_key="folders")
    remove_folders = ["System", "Utilities", "GeoprocessingServices"]
    folder_names_clean = list(set(folder_names_raw) - set(remove_folders))
    folder_names_clean.append("")
    folder_names_clean.sort()

    #   Assign the folder names list to the machine object variable.
    machine_object.folder_names_list = folder_names_clean
    print(f"MACHINE: {machine_object}")

    #   Need a single list containing all folder url's AND all service url's from within all of those folders.
    #   It is passed to the server and indicates the resourceURIs for which metrics will be built in the query process
    #   Use Folder objects to store folder urls and service objects containing urls
    list_of_folder_objects = [FolderObject(name=folder_name, root_machine_url=machine_object.root_url) for folder_name
                              in machine_object.folder_names_list]

    #   For each folder, need a list of service objects for services in that folder
    for fold_obj in list_of_folder_objects:

        # Need a url to which to make a request to learn the services within
        services_request_response = get_response(url=fold_obj.folder_machine_url, params=basic_secure_params)
        services_json = search_json_for_key(response_json=services_request_response, search_key="services")

        # Need to store the inventory of services that are within each folder
        for service in services_json:
            service_object = ServiceObject(folder=fold_obj.name,
                                           service_json=service,
                                           root_machine_url=machine_object.root_url)
            fold_obj.service_objects_list.append(service_object)

    master_url_list = create_master_url_list(list_of_folder_objects)

    # Need to create a new report object for use in generating report on server.
    report_object = ReportObject(root_machine_url=machine_object.root_url,
                                 master_urls_list=master_url_list,
                                 basic_request_json=basic_secure_params)

    # Report is created on the server. No response is needed. The variable isn't used afterward for that reason.
    print("Creating Report")
    usage_report_params = create_params_for_request(token_action=machine_object.token,
                                                    json_payload=report_object.report_json_params)

    print(usage_report_params)  # TESTING
    # FIXME: When I use the output params to create a report, and access the data I see "NODATA" in the columns in html
    # view. It doesn't appear that the JSON is correct or that using the machine specific model is working as desired

    get_response(url=report_object.report_url_create, params=usage_report_params)

    # Need to get the report contents using the query url
    # TODO: This is from Jessie. Not certain if it will work with the machine name model
    # NOTE: Like the usagereports dictionary it appears that any dictionary value that is a dictionary must be converted
    #   to a string first using json.dumps()
    # NOTE: Machine specific request, through browser interface, populated machine name as follows
    #   {"machines": ["GIS-AGS-IMAP02P.MDGOV.MARYLAND.GOV"]}
    print("Querying Report")
    post_data_query = {'filter': json.dumps({'machines': '*'})}
    report_query_params = create_params_for_request(token_action=machine_object.token,
                                                    json_payload=post_data_query,
                                                    response_format='csv')
    report_query_response = get_response(url=report_object.report_url_query, params=report_query_params)

    # Need to write the report content to csv file
    print("Writing CSV")
    write_response_to_csv(response=report_query_response, csv_path=CSV_OUTPUT_FILE_PATH)

    # Need to delete the report from the server to reduce bloat
    print("Deleting Report")
    # report_delete_params = create_params_for_request(token_action=machine_object.token)
    get_response(url=report_object.report_url_delete, params=basic_secure_params)

    print("Complete!")


if __name__ == "__main__":
    main()
