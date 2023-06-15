import deploy_capella_deploy
import string
import random

username = "abhay.aggrawal@couchbase.com"
password = "Dobara#22429"
url = "https://api.sbx-1.sandbox.nonprod-project-avengers.com"
varialeDict=dict()
tenantID = "640bd963-a3d4-4173-88fa-1f4257c9abbd"
deploy = deploy_capella_deploy.CapellaDeployments(username, password, tenantID, url)
deploy.getJwtToken(varialeDict)

projectName = ''.join(random.choices(string.ascii_uppercase +
                             string.digits, k=8))
deploy.createProject(projectName)
deploy.deleteProject()