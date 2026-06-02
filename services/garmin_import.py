import requests

def get_garmin_data():

 url="https://apis.garmin.com/wellness-api/rest/heartRate"

 headers={
"Authorization":"Bearer TOKEN"
}

 r=requests.get(url,headers=headers)

 data=r.json()
 return data