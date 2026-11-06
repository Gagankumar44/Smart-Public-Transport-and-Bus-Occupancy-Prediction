"""Preview controls must never change the production transport source."""
from fastapi.testclient import TestClient
from app import main,feeds,demo_preview as preview

def test_preview_pause_restart_and_source_isolation(monkeypatch):
 monkeypatch.setenv('RUSHLESS_DATA_MODE','schedule')
 points=[[main.stop(s)['lat'],main.stop(s)['lon']] for s in main.ROUTES[0]['stops']]
 cumulative=[0.]
 for a,b in zip(points,points[1:]):cumulative.append(cumulative[-1]+feeds.distance(a,b))
 monkeypatch.setattr(preview,'_geometry_key',None)
 monkeypatch.setattr(preview,'geometry',lambda:(points,list(range(len(points))),cumulative,'Test stop-segment fixture'))
 monkeypatch.setattr(preview,'simulation',main.Simulation());monkeypatch.setattr(preview,'paused',False)
 client=TestClient(main.app);production_generation=main.sim.generation
 restarted=client.post('/api/tracking/demo-preview',json={'action':'restart'}).json()
 assert restarted['source']=='simulation' and restarted['live_connected'] is False
 assert restarted['vehicle']['metadata']['source']=='simulation'
 paused=client.post('/api/tracking/demo-preview',json={'action':'pause'}).json()
 again=client.get('/api/tracking/demo-preview').json()
 assert paused['clock']==again['clock'] and paused['vehicle']['lat']==again['vehicle']['lat']
 assert again['paused'] and again['vehicle']['paused']
 resumed=client.post('/api/tracking/demo-preview',json={'action':'resume'}).json()
 assert not resumed['paused'] and resumed['generation']==paused['generation']
 reset=client.post('/api/tracking/demo-preview',json={'action':'restart'}).json()
 assert reset['generation']!=paused['generation']
 assert feeds.mode()=='schedule' and main.sim.generation==production_generation
 assert client.post('/api/tracking/demo-preview',json={'action':'invent'}).status_code==422
