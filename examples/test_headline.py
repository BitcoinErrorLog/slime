"""The headline acceptance test's data path, run offline against the fixtures.

Covers what files can show: discovery from a signed advertisement, slice import into
a local index, query responses, notices, dependency tracking, and publishing failover through
a route and a home statement. It does not show that an App boots offline, that Ring issues a
delegation, or that a homeserver accepts a write.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy,json,shutil,socket,tempfile,unittest
from check_sets import (InvalidSet,LocalIndex,accepts_notice,check_delegation,check_entries,check_slice,
                        check_provider,derive,entry_in_scope,parse,providers_for,resolve_home,sha,
                        verify_candidates,verify_home,verify_notice,verify_provider,verify_route,
                        verify_set,verify_signature,verify_slice)

E=Path(__file__).resolve().parent
H=E/'headline'
EXPECTED=json.loads((E/'expected.json').read_text())
HX=EXPECTED['headline']
ID=HX['identities']
URI=HX['uris']
DELEGATIONS=json.loads((H/'delegations.json').read_text())
NOW=datetime(2026,9,25,12,30,0,tzinfo=timezone.utc)

def read(*parts):
    return (H.joinpath(*parts)).read_bytes()

def signed(*parts):
    name=parts[-1]
    return read(*parts),read(*parts[:-1],name[:-len('.json')]+'.sig.json')

def advertisement():
    return verify_provider(*signed('bob-provider','provider.json'),DELEGATIONS['bob'],NOW)

def carol_tag():
    return read('carol-notice','records',URI['carol_tag'][len('pubky://'):])

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
        # Alice follows Dana. Her mesh holds Bob's advertisement: Bob chose to share Dana's key.
        ad=advertisement()
        chosen=providers_for([ad],ID['dana'],'slices',NOW)
        self.assertEqual([a['provider'] for a in chosen],[ID['bob_provider']])
        # She imports Bob's first slice and builds her own index from the bytes.
        first=verify_slice(E/'headline/bob-slice-1',expected_provider=ad['provider'])
        index=LocalIndex()
        self.assertEqual(index.admit_set(first),5)
        self.assertEqual(index.query('author',key=ID['dana']),sorted([URI['shop'],URI['shirt'],URI['print'],URI['blob']]))
        self.assertEqual(index.query('refs',uri=URI['shirt'],kind='tag'),[URI['curator_tag']])
        self.assertEqual(index.query('label',label='local-print'),[URI['curator_tag']])
        self.assertEqual(index.dependencies(URI['print']),[(URI['blob'],'retained')])
        # Carol tags print-2 and notifies a provider that serves Dana's key. Bob accepts and checks it.
        notice=verify_notice(read('carol-notice','notice.json'),URI['carol_tag'],carol_tag())
        self.assertTrue(accepts_notice(notice,ID['bob_provider'],None,ad))
        # Alice asks Bob's endpoint for tags on print-2 after the slice's last seq.
        answer=verify_candidates(read('bob-answers','refs-print-2-tags.json'),ad)
        self.assertEqual(answer['query']['after'],first['slice']['through'])
        [candidate]=answer['entries']
        self.assertTrue(index.admit(candidate['uri'],carol_tag(),candidate['sha256'],candidate))
        self.assertEqual(index.query('refs',uri=URI['print'],kind='tag'),[URI['carol_tag']])
        self.assertEqual(index.query('label',label='great-print'),[URI['carol_tag']])
        # Bob's next snapshot carries the same tag; importing it adds nothing twice.
        second=verify_slice(E/'headline/bob-slice-2',expected_provider=ad['provider'])
        self.assertEqual(second['previous'],first['id'])
        self.assertEqual(second['id'],ad['slices'][0]['set'])
        self.assertEqual(index.admit_set(second),0)
        self.assertEqual(len(index),6)
        # Alice's primary refuses her writes; her failover key's statement names the alternate.
        route=signed('alice-route','route.json')
        home=signed('alice-route','home.json')
        rejected=[signed('alice-route','rejected','unenrolled-home.json'),signed('alice-route','rejected','wrong-signer-home.json')]
        resolved=resolve_home(ID['alice'],[route],rejected+[home],DELEGATIONS['alice'],NOW)
        self.assertEqual(resolved,{'home':ID['homeserver_alternate'],'via':'failover','sequence':1})
        self.assertEqual(resolve_home(ID['alice'],[route],rejected,DELEGATIONS['alice'],NOW)['home'],ID['homeserver_primary'])

    def test_author_answer_matches_slice(self):
        answer=verify_candidates(read('bob-answers','author-dana.json'),advertisement())
        first=verify_slice(E/'headline/bob-slice-1')
        dana={(e['uri'],e['sha256']) for e in first['slice']['entries'] if e['uri'].startswith('pubky://'+ID['dana']+'/')}
        self.assertEqual({(e['uri'],e['sha256']) for e in answer['entries']},dana)

    def test_route_names_bob_for_notices(self):
        route=verify_route(*signed('alice-route','route.json'),ID['alice'])
        self.assertIn(ID['bob_provider'],[p['provider'] for p in route['notice']])
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

class Sharing(NoNetwork):
    """Scopes are the published form of a user's share and don't-share choices."""
    def entries(self):
        return verify_slice(E/'headline/bob-slice-2')['slice']['entries']
    def covered(self,scopes):
        return {e['uri'] for e in self.entries() if entry_in_scope(e,scopes)}
    def test_share_a_key(self):
        self.assertEqual(len(self.covered([{'key':ID['dana']}])),6)
    def test_share_a_key_without_tags(self):
        self.assertEqual(self.covered([{'key':ID['dana'],'kinds':['other','blob']}]),{URI['shop'],URI['shirt'],URI['print'],URI['blob']})
    def test_share_one_listing(self):
        self.assertEqual(self.covered([{'uri':URI['print']}]),{URI['print'],URI['carol_tag']})
    def test_share_a_label(self):
        self.assertEqual(self.covered([{'label':'great-print'}]),{URI['carol_tag']})
    def test_slice_must_match_choices(self):
        result=verify_slice(E/'headline/bob-slice-2')
        doc=copy.deepcopy(result['slice']);doc['scopes']=[{'uri':URI['print']}]
        with self.assertRaises(InvalidSet):check_slice(doc,result['versions'])

class Advertisements(NoNetwork):
    def test_tampered_advertisement(self):
        raw,sig=signed('bob-provider','provider.json')
        with self.assertRaises(InvalidSet):verify_provider(raw.replace(b'"sequence": 2',b'"sequence": 3'),sig)
    def test_provider_signature_is_not_a_set_signature(self):
        with self.assertRaises(InvalidSet):verify_signature(*signed('bob-provider','provider.json'),'set')
    def test_set_signature_is_not_an_advertisement(self):
        d=E/'headline/bob-slice-1'
        with self.assertRaises(InvalidSet):verify_provider((d/'set.json').read_bytes(),(d/'set.sig.json').read_bytes())
    def test_expired_advertisement(self):
        with self.assertRaises(InvalidSet):
            verify_provider(*signed('bob-provider','provider.json'),now=datetime(2026,11,1,tzinfo=timezone.utc))
    def test_undelegated_provider_key(self):
        with self.assertRaises(InvalidSet):verify_provider(*signed('bob-provider','provider.json'),DELEGATIONS['alice'],NOW)
        revoked=copy.deepcopy(DELEGATIONS['bob']);revoked['app_keys']=[]
        with self.assertRaises(InvalidSet):verify_provider(*signed('bob-provider','provider.json'),revoked,NOW)
    def test_delegation_needs_time(self):
        with self.assertRaises(InvalidSet):verify_provider(*signed('bob-provider','provider.json'),DELEGATIONS['bob'])
    def test_live_role_needs_endpoint(self):
        ad=copy.deepcopy(advertisement());del ad['endpoints']
        with self.assertRaises(InvalidSet):check_provider(ad)
    def test_slices_role_and_list_agree(self):
        ad=copy.deepcopy(advertisement());ad['roles'].remove('slices')
        with self.assertRaises(InvalidSet):check_provider(ad)
    def test_self_peer(self):
        ad=copy.deepcopy(advertisement());ad['peers'].append({'operator':ad['operator'],'provider':ad['provider']})
        with self.assertRaises(InvalidSet):check_provider(ad)
    def test_identity_key_is_not_a_provider_key(self):
        ad=copy.deepcopy(advertisement());ad['provider']=ad['operator']
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
    def test_entry_kind_must_match_bytes(self):
        doc,versions=self.slice_doc()
        doc['entries'][1]['kind']='post'
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
    def test_entries_only_slice_is_allowed(self):
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
    def test_listing_kinds_are_not_slime_kinds(self):
        doc,_=self.slice_doc()
        doc['entries'][1]['kind']='listing'
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
        with self.assertRaises(InvalidSet):self.check(self.answer('author-dana.json'),ad)
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
    def notice(self):
        return verify_notice(read('carol-notice','notice.json'),URI['carol_tag'],carol_tag())
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
    def test_listed_provider_accepts(self):
        route=verify_route(*signed('alice-route','route.json'),ID['alice'])
        to_alice=dict(self.notice(),target='pubky://'+ID['alice']+'/')
        self.assertTrue(accepts_notice(to_alice,ID['bob_provider'],route,None))
        self.assertFalse(accepts_notice(to_alice,ID['other_provider'],route,None))
    def test_scope_provider_accepts_only_for_its_scope(self):
        ad=advertisement()
        self.assertTrue(accepts_notice(self.notice(),ad['provider'],None,ad))
        to_alice=dict(self.notice(),target='pubky://'+ID['alice']+'/')
        self.assertFalse(accepts_notice(to_alice,ad['provider'],None,ad))
        quiet=copy.deepcopy(ad);quiet['roles'].remove('notices')
        self.assertFalse(accepts_notice(self.notice(),ad['provider'],None,quiet))

class Failover(NoNetwork):
    def home(self,*path,**kw):
        path=path or ('home.json',)
        args=dict(identity=ID['alice'],route=read('alice-route','route.json'),
                  route_sidecar=read('alice-route','route.sig.json'),delegation=DELEGATIONS['alice'],now=NOW)
        args.update(kw)
        return verify_home(*signed('alice-route',*path),**args)
    def test_valid_statement(self):
        self.assertEqual(self.home()['home'],ID['homeserver_alternate'])
    def test_route_signed_by_identity(self):
        with self.assertRaises(InvalidSet):verify_route(*signed('alice-route','route.json'),ID['bob'])
        with self.assertRaises(InvalidSet):verify_route(read('alice-route','route.json'),read('bob-provider','provider.sig.json'),ID['alice'])
    def test_route_signature_is_not_a_home_signature(self):
        with self.assertRaises(InvalidSet):verify_signature(*signed('alice-route','route.json'),'home')
    def test_home_must_be_enrolled(self):
        with self.assertRaises(InvalidSet):self.home('rejected','unenrolled-home.json')
    def test_signer_must_be_routes_failover_key(self):
        with self.assertRaises(InvalidSet):self.home('rejected','wrong-signer-home.json')
    def test_failover_key_must_be_delegated(self):
        revoked=copy.deepcopy(DELEGATIONS['alice']);revoked['app_keys']=[]
        with self.assertRaises(InvalidSet):self.home(delegation=revoked)
        with self.assertRaises(InvalidSet):self.home(delegation=DELEGATIONS['bob'])
    def test_expired_delegation(self):
        with self.assertRaises(InvalidSet):self.home(now=datetime(2027,3,21,tzinfo=timezone.utc))
    def test_stale_statement(self):
        with self.assertRaises(InvalidSet):self.home(last_sequence=1)
        self.assertEqual(self.home(last_sequence=0)['sequence'],1)
    def test_statement_bound_to_route(self):
        with self.assertRaises(InvalidSet):self.home(route=read('alice-route','route.json')+b'\n')
    def test_no_valid_route(self):
        forged=(read('alice-route','route.json'),read('alice-route','home.sig.json'))
        with self.assertRaises(InvalidSet):resolve_home(ID['alice'],[forged],[],DELEGATIONS['alice'],NOW)
    def test_delegation_shape(self):
        with self.assertRaises(InvalidSet):check_delegation(DELEGATIONS['alice'],ID['alice'],ID['alice_failover'],'xyz',NOW)
        wrong_app=dict(DELEGATIONS['alice'],app_id='paykit')
        with self.assertRaises(InvalidSet):check_delegation(wrong_app,ID['alice'],ID['alice_failover'],DELEGATIONS['alice']['app_keys'][0]['cert_id'],NOW)

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
        self.assertEqual(index.dependencies(URI['print']),[(URI['blob'],'missing')])
    def test_blob_name_must_match_bytes(self):
        with self.assertRaises(InvalidSet):derive(URI['blob'],b'other bytes')
    def test_unknown_types_are_indexed_by_their_references(self):
        dana='pubky://'+ID['dana']
        body=json.dumps({'a':{'b':[URI['print'],dana,'https://example.org/x',dana+'/priv/secret','plain']}}).encode()
        self.assertEqual(derive(dana+'/pub/some.app/items/1',body),
                         {'kind':'other','refs':sorted([URI['print'],dana+'/','https://example.org/x'])})
        self.assertEqual(derive(dana+'/pub/some.app/items/2',b'\x00binary'),{'kind':'other'})
        self.assertEqual(derive(dana+'/pub/some.app/items/3',b'{}'),{'kind':'other'})
    def test_import_order_independent(self):
        a,b=LocalIndex(),LocalIndex()
        first,second=verify_slice(E/'headline/bob-slice-1'),verify_slice(E/'headline/bob-slice-2')
        a.admit_set(first);a.admit_set(second);b.admit_set(second);b.admit_set(first)
        for op,args in [('author',{'key':ID['dana']}),('label',{'label':'great-print'}),('refs',{'uri':URI['print']})]:
            self.assertEqual(a.query(op,**args),b.query(op,**args))

if __name__=='__main__':unittest.main()
