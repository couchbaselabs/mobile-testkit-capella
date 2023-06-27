from libraries.provision import deploy_capella_deploy
from keywords.MobileRestClient import MobileRestClient
import string
import random
import json
import time 

def setupAppService(username, password, url, tenantId):
# username = "abhay.aggrawal@couchbase.com"
# password = "Dobara#22429"
# url = "https://api.dev.nonprod-project-avengers.com"
        varialeDict=dict()
# tenantID = "6af08c0a-8cab-4c1c-b257-b521575c16d0"
        deploy = deploy_capella_deploy.CapellaDeployments(username, password, tenantId, url)
        deploy.getJwtToken(varialeDict)

        projectName ="mobile-" + ''.join(random.choices(string.ascii_uppercase +
                             string.digits, k=8))
        deploy.createProject(projectName)

        clustertemplateFile = "libraries/provision/quick-3.json"
        with open(clustertemplateFile, 'r') as file:
             clustertemplate = json.load(file)
        deploy.deployCluster("mobile", "us-west-2", "aws", clustertemplate)
        deploy.waitForClusterHealth()
        time.sleep(10)
        bucketTemplateFile = "libraries/provision/bucket_template.json"
        with open(bucketTemplateFile) as file:
            file_contents = file.read()
        buckettemplate = json.loads(file_contents)
        deploy.createBucket(buckettemplate)
        instanceType = "c5.2xlarge"
        deploy.createAppService(instanceType)
        deploy.waitForAppServiceHealth()
        deploy.createAppEndpoint()
        deploy.getAppEndPointUrls()
        return deploy.AppServiceSetup()
        # deploy.deleteProject()

# obj = MobileRestClient()
# auth = ("user","Password123,")
# obj.request_session("https://ozlhhjh1zd8la6tc.apps.nonprod-project-avengers.com:4984/appendpoint", "user", password="Password123,", auth=auth)
