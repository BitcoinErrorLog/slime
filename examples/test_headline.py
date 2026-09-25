"""The headline acceptance test's data path, run offline against the fixtures.

Covers what files can show: discovery from a signed advertisement, slice import into a
local index, query responses, notices, dependency tracking, and the failover route.
It does not show that an App boots offline or that a homeserver accepts a write.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy,json,shutil,socket,tempfile,unittest
from check_sets import (InvalidSet,LocalIndex,check_entries,check_provider,check_slice,derive,parse,
                        parse_txt,providers_for,resolve_home,sha,verify_candidates,verify_notice,
                        verify_provider,verify_set,verify_signature,verify_slice)

E=Path(__file__).resolve().parent
H=E/'headline'
EXPECTED=json.loads((E/'expected.json').read_text())
HX=EXPECTED['headline']
ID=HX['identities']
URI=HX['uris']
NOW=datetime(2026,9,25,12,0,0,tzinfo=timezone.utc)

def read(*parts):
    return (H.joinpath(*parts)).read_bytes()

def advertisement():
    return verify_provider(read('bob-provider','provider.json'),read('bob-provider','provider.sig.json'),NOW)

def carol_tag():
    return read('carol-notice','records',URI['carol_tag'][len('pubky://'):])

def txt(name):
    return read('alice-route',name).decode().rstrip('\n')

class NoNetwork(unittest.TestCase):
    """Every test in this module runs with sockets disabled."""
    def setUp(self):
        self._socket=socket.socket
        def refuse(*args,**kwargs):
            raise AssertionError('network access attempted')
        socket.socket=refuse
    def tearDown(self):
        socket.socket=self._socket

class Headline(NoNetwork):
    def test_headline_data_path(self):
        # Alice follows Dana. Her mesh holds Bob's advertisement, which retains Dana's key.
        ad=advertisement()
        chosen=providers_for([ad],ID['dana'],'slices',NOW)
        self.assertEqual([a['provider'] for a in chosen],[ID['bob_provider']])
        # She imports Bob's first slice and builds her own index from the bytes.
        first=verify_slice(E/'headline/bob-slice-1',expected_provider=ad['provider'])
        index=LocalIndex()
        self.assertEqual(index.admit_set(first),5)
        self.assertEqual(index.query('author',key=ID['dana'],kind='listing'),sorted([URI['shirt'],URI['print']]))
        self.assertEqual(index.query('refs',uri=URI['shirt'],kind='tag'),[URI['curator_tag']])
        self.assertEqual(index.query('label',label='local-print'),[URI['curator_tag']])
        self.assertEqual(index.dependencies(URI['print']),sorted([(URI['blob'],'retained'),(URI['shop'],'retained')]))
        # Carol tags print-2 and notifies Dana's notice providers. Bob checks the source.
        notice=verify_notice(read('carol-notice','notice.json'),URI['carol_tag'],carol_tag())
        self.assertEqual(notice['target'],URI['print'])
        # Alice asks Bob's endpoint for tags on print-2 after the slice's last seq.
        answer=verify_candidates(read('bob-answers','refs-print-2-tags.json'),ad)
        self.assertEqual(answer['query']['after'],first['slice']['through'])
        [candidate]=answer['entries']
        self.assertTrue(index.admit(candidate['uri'],carol_tag(),candidate['sha256'],candidate))
        self.assertEqual(index.query('refs',uri=URI['print'],kind='tag'),[URI['carol_tag']])
        self.assertEqual(index.query('label',label='great-print'),[URI['carol_tag']])
        # Bob's next slice carries the same tag; importing it adds nothing twice.
        second=verify_slice(E/'headline/bob-slice-2',expected_provider=ad['provider'])
        self.assertEqual(second['previous'],first['id'])
        self.assertEqual(second['id'],ad['slices'][0]['set'])
        self.assertEqual(index.admit_set(second),0)
        self.assertEqual(len(index),6)
        # Alice's primary homeserver refuses her writes; her failover key names the alternate.
        route=read('alice-route','route.json')
        home=resolve_home(ID['alice'],route,txt('identity.txt'),ID['alice_failover'],txt('failover.txt'),NOW)
        self.assertEqual(home,{'home':ID['homeserver_alternate'],'via':'failover','seq':1})
        self.assertEqual(resolve_home(ID['alice'],route,txt('identity.txt'))['home'],ID['homeserver_primary'])

    def test_listing_answer_matches_slice(self):
        ad=advertisement()
        answer=verify_candidates(read('bob-answers','author-dana-listings.json'),ad)
        first=verify_slice(E/'headline/bob-slice-1')
        listed={(e['uri'],e['sha256']) for e in first['slice']['entries'] if e['kind']=='listing'}
        self.assertEqual({(e['uri'],e['sha256']) for e in answer['entries']},listed)

    def test_route_is_in_notice_path(self):
        route=parse(read('alice-route','route.json'),'route')
        self.assertIn(ID['bob_provider'],route['notice'])
        self.assertEqual('sha256:'+sha(read('alice-route','route.json')),HX['route'])

    def test_fixtures_carry_no_private_or_ranking_fields(self):
        forbidden={'favorite','favorites','search','searches','query_log','score','rank','ranking','order',
                   'orders','buyer','customer_address','invoice','payment_request','mnemonic','private_key','seed'}
        for path in H.rglob('*.json'):
            def scan(x):
                if isinstance(x,dict):
                    self.assertFalse(forbidden.intersection(x),path)
                    for v in x.values():scan(v)
                elif isinstance(x,list):
                    for v in x:scan(v)
            scan(json.loads(path.read_text()))

class Advertisements(NoNetwork):
    def test_tampered_advertisement(self):
        raw=read('bob-provider','provider.json').replace(b'"sequence": 2',b'"sequence": 3')
        with self.assertRaises(InvalidSet):verify_provider(raw,read('bob-provider','provider.sig.json'))
    def test_provider_signature_is_not_a_set_signature(self):
        with self.assertRaises(InvalidSet):
            verify_signature(read('bob-provider','provider.json'),read('bob-provider','provider.sig.json'),'set')
    def test_set_signature_is_not_an_advertisement(self):
        d=E/'headline/bob-slice-1'
        with self.assertRaises(InvalidSet):verify_provider((d/'set.json').read_bytes(),(d/'set.sig.json').read_bytes())
    def test_expired_advertisement(self):
        with self.assertRaises(InvalidSet):
            verify_provider(read('bob-provider','provider.json'),read('bob-provider','provider.sig.json'),
                            datetime(2026,11,1,tzinfo=timezone.utc))
    def test_live_role_needs_endpoint(self):
        ad=copy.deepcopy(advertisement());del ad['endpoints']
        with self.assertRaises(InvalidSet):check_provider(ad)
    def test_slices_role_and_list_agree(self):
        ad=copy.deepcopy(advertisement());ad['roles'].remove('slices')
        with self.assertRaises(InvalidSet):check_provider(ad)
    def test_self_peer(self):
        ad=copy.deepcopy(advertisement());ad['peers'].append(ad['provider'])
        with self.assertRaises(InvalidSet):check_provider(ad)
    def test_newest_sequence_wins_and_scope_filters(self):
        ad=advertisement();older=copy.deepcopy(ad);older['sequence']=1
        self.assertEqual(providers_for([older,ad],ID['dana'],'query',NOW)[0]['sequence'],2)
        self.assertEqual(providers_for([ad],ID['carol'],'query',NOW),[])
    def test_unknown_role_rejected(self):
        raw=json.loads(read('bob-provider','provider.json'));raw['roles'].append('rank')
        with self.assertRaises(InvalidSet):parse(json.dumps(raw).encode(),'provider')

class Slices(NoNetwork):
    def slice_doc(self):
        result=verify_slice(E/'headline/bob-slice-2')
        return copy.deepcopy(result['slice']),result['versions']
    def test_entry_must_match_bytes(self):
        doc,versions=self.slice_doc()
        doc['entries'][2]['label']='forged'
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_entry_refs_must_match_bytes(self):
        doc,versions=self.slice_doc()
        doc['entries'][4]['refs']=[URI['shop']]
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_entry_outside_scope(self):
        doc,versions=self.slice_doc()
        doc['scopes']=[{'key':ID['carol']}]
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_body_without_entry(self):
        doc,versions=self.slice_doc()
        doc['entries'].pop()
        doc['through']='5'
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_seq_order(self):
        doc,_=self.slice_doc()
        doc['entries'][0],doc['entries'][1]=doc['entries'][1],doc['entries'][0]
        with self.assertRaises(InvalidSet):check_entries(doc['entries'])
    def test_through_below_last(self):
        doc,versions=self.slice_doc()
        doc['through']='3'
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_thin_slice_entries_are_allowed(self):
        doc,_=self.slice_doc()
        self.assertEqual(check_slice(doc,{}),6)
    def test_slice_must_be_signed_by_its_provider(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'s';shutil.copytree(E/'headline/bob-slice-1',dest)
            (dest/'set.sig.json').unlink()
            with self.assertRaises(InvalidSet):verify_slice(dest)
    def test_other_provider_pin(self):
        with self.assertRaises(InvalidSet):verify_slice(E/'headline/bob-slice-1',expected_provider=ID['carol'])
    def test_tampered_slice(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'s';shutil.copytree(E/'headline/bob-slice-1',dest)
            p=dest/'slice.json';p.write_bytes(p.read_bytes().replace(b'local-print',b'local-prinz'))
            with self.assertRaises(InvalidSet):verify_slice(dest)
    def test_score_field_rejected(self):
        doc,_=self.slice_doc()
        doc['entries'][0]['score']=9
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')
    def test_label_only_on_tags(self):
        doc,_=self.slice_doc()
        doc['entries'][0]['label']='x'
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')
    def test_tag_needs_label(self):
        doc,_=self.slice_doc()
        del doc['entries'][2]['label']
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')

class Answers(NoNetwork):
    def answer(self,name='refs-print-2-tags.json'):
        return json.loads(read('bob-answers',name))
    def check(self,doc,ad=None):
        return verify_candidates(json.dumps(doc).encode(),ad)
    def test_rank_field_rejected(self):
        doc=self.answer();doc['entries'][0]['rank']=1
        with self.assertRaises(InvalidSet):self.check(doc)
    def test_entry_must_match_query(self):
        doc=self.answer();doc['query']['uri']=URI['shirt']
        with self.assertRaises(InvalidSet):self.check(doc)
    def test_entry_after_cursor(self):
        doc=self.answer();doc['query']['after']='6'
        with self.assertRaises(InvalidSet):self.check(doc)
    def test_incomplete_needs_next(self):
        doc=self.answer();doc['complete']=False
        with self.assertRaises(InvalidSet):self.check(doc)
        doc['next']='6'
        self.assertFalse(self.check(doc)['complete'])
        doc['next']='5'
        with self.assertRaises(InvalidSet):self.check(doc)
    def test_outside_advertised_scope(self):
        ad=copy.deepcopy(advertisement());ad['scopes']=[{'key':ID['carol']},{'label':'other'}]
        doc=self.answer('author-dana-listings.json')
        with self.assertRaises(InvalidSet):self.check(doc,ad)
    def test_other_provider(self):
        ad=copy.deepcopy(advertisement());ad['provider']=ID['carol']
        with self.assertRaises(InvalidSet):self.check(self.answer(),ad)
    def test_label_scope_admits_tag(self):
        ad=copy.deepcopy(advertisement());ad['scopes']=[{'label':'great-print'}]
        self.assertEqual(len(self.check(self.answer(),ad)['entries']),1)
    def test_gone_entry(self):
        doc=self.answer();doc['entries']=[{'gone':True,'kind':'tag','seq':'7','uri':URI['carol_tag']}]
        self.assertTrue(self.check(doc)['entries'][0]['gone'])
        doc['entries'][0]['sha256']='0'*64
        with self.assertRaises(InvalidSet):self.check(doc)
    def test_domain_primitive(self):
        index=LocalIndex()
        index.admit_set(verify_set(E/'github-signed'))
        self.assertEqual(len(index.query('domain',host='github.com')),1)
        self.assertEqual(index.query('domain',host='example.org'),[])

class Notices(NoNetwork):
    def test_target_must_be_referenced(self):
        doc=json.loads(read('carol-notice','notice.json'));doc['target']=URI['shirt']
        with self.assertRaises(InvalidSet):verify_notice(json.dumps(doc).encode(),URI['carol_tag'],carol_tag())
    def test_source_hash(self):
        with self.assertRaises(InvalidSet):verify_notice(read('carol-notice','notice.json'),URI['carol_tag'],carol_tag()+b' ')
    def test_bare_key_target(self):
        doc=json.loads(read('carol-notice','notice.json'));doc['target']='pubky://'+ID['dana']+'/'
        self.assertEqual(verify_notice(json.dumps(doc).encode(),URI['carol_tag'],carol_tag())['target'],doc['target'])
    def test_wrong_source(self):
        with self.assertRaises(InvalidSet):verify_notice(read('carol-notice','notice.json'),URI['curator_tag'],carol_tag())
    def test_notice_carries_no_body(self):
        doc=json.loads(read('carol-notice','notice.json'));doc['text']='hello'
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'notice')

class Failover(NoNetwork):
    def route(self):
        return read('alice-route','route.json')
    def resolve(self,**kw):
        args=dict(identity=ID['alice'],route=self.route(),identity_txt=txt('identity.txt'),
                  failover_key=ID['alice_failover'],failover_txt=txt('failover.txt'),now=NOW)
        args.update(kw)
        return resolve_home(**args)
    def test_pin_mismatch(self):
        with self.assertRaises(InvalidSet):self.resolve(route=self.route().replace(b'"sequence": 1',b'"sequence": 2'))
    def test_wrong_identity(self):
        with self.assertRaises(InvalidSet):self.resolve(identity=ID['bob'])
    def test_unnamed_failover_key(self):
        with self.assertRaises(InvalidSet):self.resolve(failover_key=ID['bob'])
    def test_home_must_be_enrolled(self):
        bad=txt('failover.txt').replace(ID['homeserver_alternate'],ID['carol'])
        with self.assertRaises(InvalidSet):self.resolve(failover_txt=bad)
    def test_expired_authority(self):
        with self.assertRaises(InvalidSet):self.resolve(now=datetime(2027,3,21,tzinfo=timezone.utc))
        with self.assertRaises(InvalidSet):self.resolve(now=None)
    def test_stale_record(self):
        with self.assertRaises(InvalidSet):self.resolve(last_seq=1)
        self.assertEqual(self.resolve(last_seq=0)['seq'],1)
    def test_other_route_version(self):
        bad=txt('failover.txt').rsplit(' rt=',1)[0]+' rt='+'0'*64
        with self.assertRaises(InvalidSet):self.resolve(failover_txt=bad)
    def test_txt_rules(self):
        self.assertEqual(parse_txt('v=slime1 rt=ab')['rt'],'ab')
        for bad in ['rt=ab v=slime1','v=slime1 rt=ab rt=cd','v=slime1  rt=ab','v=slime2 rt=ab','v=slime1 RT=ab',
                    'v=slime1 rt=','v=slime1 '+'x='+'a'*260,'v=slime1 rt=\u00e9']:
            with self.subTest(bad=bad),self.assertRaises(InvalidSet):parse_txt(bad)
    def test_route_without_failover(self):
        doc=json.loads(self.route());del doc['failover']
        raw=json.dumps(doc).encode()
        with self.assertRaises(InvalidSet):self.resolve(route=raw,identity_txt='v=slime1 rt='+sha(raw))

class Index(NoNetwork):
    def test_wrong_bytes_rejected(self):
        with self.assertRaises(InvalidSet):LocalIndex().admit(URI['carol_tag'],carol_tag(),'0'*64)
    def test_lying_candidate_rejected(self):
        entry=json.loads(read('bob-answers','refs-print-2-tags.json'))['entries'][0]
        entry['refs']=[URI['shirt']]
        with self.assertRaises(InvalidSet):LocalIndex().admit(entry['uri'],carol_tag(),entry['sha256'],entry)
    def test_missing_dependency_reported(self):
        index=LocalIndex()
        first=verify_slice(E/'headline/bob-slice-1')
        for (origin,digest),raw in first['versions'].items():
            if origin!=URI['blob']:index.admit(origin,raw,digest)
        self.assertIn((URI['blob'],'missing'),index.dependencies(URI['print']))
        self.assertIn((URI['shop'],'retained'),index.dependencies(URI['print']))
    def test_blob_name_must_match_bytes(self):
        with self.assertRaises(InvalidSet):derive(URI['blob'],b'other bytes')
    def test_foreign_namespace_is_opaque(self):
        self.assertEqual(derive('pubky://'+ID['dana']+'/pub/pubky.app/posts/0001','{}'.encode()),{'kind':'other'})
    def test_import_order_independent(self):
        a,b=LocalIndex(),LocalIndex()
        first,second=verify_slice(E/'headline/bob-slice-1'),verify_slice(E/'headline/bob-slice-2')
        a.admit_set(first);a.admit_set(second);b.admit_set(second);b.admit_set(first)
        for op,args in [('author',{'key':ID['dana']}),('label',{'label':'great-print'}),('refs',{'uri':URI['print']})]:
            self.assertEqual(a.query(op,**args),b.query(op,**args))

if __name__=='__main__':unittest.main()
