"""Gate 14 real Firefox audit; run from checkout with venv/bin/python -B tests/gate14_firefox.py."""
import base64,json,os,socket,subprocess,time,urllib.request,tempfile
from pathlib import Path
root=Path('/tmp/mimic14gate');profile=Path(tempfile.mkdtemp(prefix='firefox-profile-',dir=root))
(profile/'user.js').write_text('''user_pref("marionette.port", 2845);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("app.update.auto", false);
user_pref("browser.safebrowsing.downloads.enabled", false);
user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
''')
server=subprocess.Popen(['/home/sanmirg/mimic/venv/bin/python','-c',"from mimic.api import create_app; import uvicorn; uvicorn.run(create_app(data_dir='/tmp/mimic14gate/browser-data'), host='127.0.0.1',port=8795)"],stdout=(root/'server.log').open('w'),stderr=subprocess.STDOUT)
firefox=subprocess.Popen(['/usr/bin/firefox-esr','--headless','--no-remote','--profile',str(profile),'--marionette','--remote-allow-system-access','about:blank'],stdout=(root/'firefox.log').open('w'),stderr=subprocess.STDOUT)
class Marionette:
 def __init__(self):
  for _ in range(100):
   try:self.s=socket.create_connection(('127.0.0.1',2845),timeout=2);break
   except OSError:time.sleep(.1)
  self.s.settimeout(20);self.buffer=b'';self.index=0;self.read()
 def read(self):
  while b':' not in self.buffer:self.buffer+=self.s.recv(65536)
  n,body=self.buffer.split(b':',1);n=int(n)
  while len(body)<n:body+=self.s.recv(65536)
  self.buffer=body[n:];return json.loads(body[:n])
 def call(self,name,params={}):
  self.index+=1;packet=json.dumps([0,self.index,name,params]).encode();self.s.sendall(str(len(packet)).encode()+b':'+packet)
  response=self.read()
  if response[2]:raise RuntimeError(response)
  result=response[3];return result.get('value',result) if isinstance(result,dict) else result
 def js(self,script):return self.call('WebDriver:ExecuteScript',{'script':script,'args':[],'newSandbox':True,'sandbox':'default'})
 def navigate(self,url):return self.call('WebDriver:Navigate',{'url':url})
 def wait(self,predicate):
  for _ in range(150):
   result=self.js(predicate)
   if result:return result
   time.sleep(.1)
  raise AssertionError(predicate)
try:
 m=Marionette();m.call('WebDriver:NewSession',{'capabilities':{'alwaysMatch':{}}})
 m.call('Marionette:SetContext',{'value':'chrome'});m.js("document.documentElement.style.minWidth='0px';document.documentElement.style.minHeight='0px';");m.call('Marionette:SetContext',{'value':'content'})
 base='http://127.0.0.1:8795'
 for _ in range(60):
  try:urllib.request.urlopen(base+'/api/health');break
  except OSError:time.sleep(.1)
 report=[]
 paths=['/services','/services?category=common','/services?q=no-such-service','/services?q=SONAR','/services?q=%22%3E%3Cscript%3Ewindow.GATE14_XSS%3D1%3C%2Fscript%3E']+['/services/'+s for s in ('zabbix','sonarqube','jenkins','tomcat','redis','opensearch')]
 for locale in ('pt-BR','en'):
  m.navigate(base+'/services');m.call('WebDriver:AddCookie',{'cookie':{'name':'mimic_locale','value':locale,'path':'/'}})
  for theme in ('dark','light'):
   m.js(f"localStorage.setItem('mimic-theme','{theme}')")
   for width in (375,768,1440):
    m.call('WebDriver:SetWindowRect',{'width':width,'height':1000})
    actual=m.js('return innerWidth')
    if actual!=width:m.call('WebDriver:SetWindowRect',{'width':width+(width-actual),'height':1000})
    for path in paths:
     m.navigate(base+path)
     result=m.js("""return {locale:document.documentElement.lang,theme:document.documentElement.dataset.theme,width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,external:[...document.querySelectorAll('script[src],link[rel=stylesheet]')].filter(x=>new URL(x.src||x.href).origin!==location.origin).length,missing:document.body.innerText.includes('catalog.service.'),references:[...document.querySelectorAll('.catalog-references a')].length,pairs:document.querySelectorAll('.catalog-credentials tbody tr').length} """)
     assert result['locale']==locale and result['theme']==theme and result['width']==width,result
     assert not result['overflow'] and not result['external'] and not result['missing'],(path,result)
     assert m.js("return !window.GATE14_XSS && !document.querySelector('script:not([src])')")
     assert m.js("return [...document.querySelectorAll('.catalog-references small')].every(e=>getComputedStyle(e).whiteSpace!=='nowrap' && e.getBoundingClientRect().width<=innerWidth)")
     if path.startswith('/services/'):
      service=path.split('/')[-1]
      assert result['references']>0 and result['pairs']==(1 if service in ('zabbix','sonarqube') else 0),(path,result)
     report.append({'path':path,**result})
     if width==375 and path=='/services/zabbix':
      data=m.call('WebDriver:TakeScreenshot',{'id':None,'full':True,'scroll':False})
      (root/f'catalog-{locale}-{theme}.png').write_bytes(base64.b64decode(data))
 # Check explicit contextual selection independently for every new service.
 for service in ('zabbix','sonarqube','jenkins','tomcat','redis','opensearch'):
  m.navigate(base+'/generate?service='+service)
  assert m.js("return [...document.querySelectorAll('[name=service_profiles]:checked')].map(x=>x.value)")==[service]
  assert m.js("return !document.querySelector('[name=include_common_passwords]').checked")
 # Keyboard-operated search and navigation.
 m.navigate(base+'/services');m.js("document.getElementById('service-search').focus()")
 m.call('WebDriver:PerformActions',{'actions':[{'type':'key','id':'keyboard','actions':[{'type':'keyDown','value':c} for c in 'Jenkins']}]});m.call('WebDriver:ReleaseActions')
 m.call('WebDriver:PerformActions',{'actions':[{'type':'key','id':'keyboard','actions':[{'type':'keyDown','value':'\ue007'},{'type':'keyUp','value':'\ue007'}]}]});m.call('WebDriver:ReleaseActions')
 m.wait("return location.search.includes('Jenkins')")
 assert m.js("return document.querySelectorAll('.catalog-service-list a').length===1 && document.querySelector('.catalog-service-list a').getAttribute('href')==='/services/jenkins'")
 m.js("document.querySelector('.catalog-service-list a').focus()")
 m.call('WebDriver:PerformActions',{'actions':[{'type':'key','id':'keyboard','actions':[{'type':'keyDown','value':'\ue007'},{'type':'keyUp','value':'\ue007'}]}]});m.call('WebDriver:ReleaseActions')
 m.wait("return location.pathname==='/services/jenkins'")
 assert m.js("return !!document.querySelector('a[href=\"/generate?service=jenkins\"]')")
 m.navigate(base+'/generate?service=jenkins')
 assert m.js("return [...document.querySelectorAll('[name=service_profiles]:checked')].map(x=>x.value).join(',')==='jenkins' && !document.querySelector('[name=include_common_passwords]').checked")
 # Tab traversal keeps controls focusable and visible.
 m.navigate(base+'/services/zabbix')
 for _ in range(18):
  m.call('WebDriver:PerformActions',{'actions':[{'type':'key','id':'tab','actions':[{'type':'keyDown','value':'\ue004'},{'type':'keyUp','value':'\ue004'}]}]});m.call('WebDriver:ReleaseActions')
  assert m.js("return document.activeElement===document.body || (document.activeElement.getBoundingClientRect().width>0 && getComputedStyle(document.activeElement).visibility!=='hidden')")
 # Hostile search remains text; no script node/event execution.
 import urllib.parse
 hostile='\"><script>window.GATE14_XSS=1</script>'
 m.navigate(base+'/services?q='+urllib.parse.quote(hostile))
 assert m.js("return !window.GATE14_XSS && !document.querySelector('script:not([src])') && document.getElementById('service-search').value.includes('GATE14_XSS')")
 assert not json.load(urllib.request.urlopen(base+'/api/jobs'))
 (root/'browser.json').write_text(json.dumps({'cases':report,'keyboard':True,'escaping':True,'opt_in':True},indent=2))
 print('PASS',len(report),'Firefox catalog layouts, keyboard search/navigation, escaping and explicit service selection')
 m.call('Marionette:Quit',{'flags':['eForceQuit']})
finally:
 firefox.terminate();server.terminate()
 try:firefox.wait(5);server.wait(5)
 except subprocess.TimeoutExpired:firefox.kill();server.kill()
