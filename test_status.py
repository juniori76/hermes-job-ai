import requests

s = requests.Session()
# Login as eduardo
login_res = s.post('http://192.168.0.123:8090/login', data={'username': 'eduardo', 'password': 'edu159753'})
print("Login status:", login_res.status_code)
print("Cookies:", s.cookies.get_dict())

res = s.post('http://192.168.0.123:8090/api/jobs/955f70324931299c5c7fa5a9decdef8c/status', json={'status': 'applied'})
print("Status code:", res.status_code)
print("Response text:", res.text)
