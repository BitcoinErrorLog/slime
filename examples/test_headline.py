"""The headline acceptance test's data path, run offline against the fixtures.

Covers what files can show: provider selection from signed advertisements, slice import into a
local index, query responses, notices and their flood rules, dependency states, Pubky grant
checks, and home statements. It does not build the configured mesh from the network, show that an
App boots offline, that Ring signs a grant, or that a homeserver accepts a write.
"""
from pathlib import Path
from datetime import datetime, timezone
import base64,copy,json,shutil,socket,tempfile,unittest
from check_sets import (InvalidSet,LocalIndex,NoticeQueue,RequestsView,accepts_notice,b3,check_entries,
                        check_grant_key,check_pow,check_provider,check_slice,entry_in_scope,grant_allows_write,
                        is_vouched,load_services,parse,resolve_home,select_providers,verify_candidates,
                        verify_grant,verify_home,verify_jws,verify_notice,verify_provider,verify_set,verify_slice)

E=Path(__file__).resolve().parent
H=E/'headline'
EXPECTED=json.loads((E/'expected.json').read_text())
ID=EXPECTED['identities']
URI=EXPECTED['uris']
NOW=datetime(2026,9,25,12,30,0,tzinfo=timezone.utc)
NOTICE_HOUR=datetime(2026,9,25,10,30,0,tzinfo=timezone.utc)
AFTER_GRANTS=datetime(2028,9,22,tzinfo=timezone.utc)
# The _pubky targets of Alice's PKARR packet, in priority order, as the PKARR library resolves them.
HOMESERVERS=[ID['homeserver_primary'],ID['homeserver_alternate']]

def read(*parts):
    return (H.joinpath(*parts)).read_bytes()

def signed(*parts):
    return read(*parts),read(*parts[:-1],parts[-1][:-len('.json')]+'.jws').decode()

def advertisement():
    return verify_provider(*signed('bob-provider','provider.json'),NOW)

def carol_tag():
    return read('carol-notice','records',URI['carol_tag'][len('pubky://'):])

def notice():
    return verify_notice(read('carol-notice','notice.json'),URI['carol_tag'],carol_tag())

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
        # Alice follows Dana. Among advertisements she holds, Bob's covers Dana's key.
        ad=advertisement()
        self.assertEqual([a['provider'] for a in select_providers([ad],{'key':ID['dana']},'slices',NOW)],[ID['bob_provider']])
        # She imports Bob's first slice and builds her own index from the bytes.
        first=verify_slice(E/'headline/bob-slice-1',expected_provider=ad['provider'])
        self.assertEqual(first['operator'],ID['bob'])
        index=LocalIndex()
        self.assertEqual(index.admit_set(first),6)
        self.assertEqual(index.query('author',key=ID['dana'],kind='post'),sorted([URI['listing'],URI['shirt']]))
        self.assertEqual(index.query('refs',uri=URI['listing'],kind='tag'),[URI['curator_tag']])
        self.assertEqual(index.query('domain',host='dana-prints.example'),sorted([URI['listing'],URI['dana_profile']]))
        self.assertEqual(index.closure(URI['listing']),sorted([(URI['blob'],'retained'),(URI['dana_profile'],'retained'),(URI['file'],'retained')]))
        # Carol tags the image post and notifies a provider that covers Dana's key.
        n=notice()
        self.assertTrue(accepts_notice(n,ID['bob_provider'],None,ad))
        check_pow(n,ad['limits']['pow_floor_bits'],NOTICE_HOUR)
        # Alice asks Bob's endpoint for tags on the post after the slice's last seq.
        answer=verify_candidates(read('bob-answers','refs-listing-tags.json'),ad)
        self.assertEqual(answer['query']['after'],first['slice']['through'])
        [candidate]=answer['entries']
        self.assertTrue(index.admit(candidate['uri'],carol_tag(),candidate['blake3'],candidate))
        self.assertEqual(index.query('label',label='great-print'),[URI['carol_tag']])
        # Bob's next snapshot carries the same tag; importing it adds nothing twice.
        second=verify_slice(E/'headline/bob-slice-2',expected_provider=ad['provider'])
        self.assertEqual(second['previous'],first['id'])
        self.assertEqual(second['id'],ad['slices'][0]['set'])
        self.assertEqual(index.admit_set(second),0)
        self.assertEqual(len(index),7)
        # Alice's primary refuses her writes; her publisher key's statement names the alternate.
        home=signed('alice-home','home.json')
        rejected=[signed('alice-home','rejected',name) for name in
                  ('unenrolled-home.json','wrong-signer-home.json','read-only-grant-home.json')]
        self.assertEqual(resolve_home(ID['alice'],HOMESERVERS,rejected+[home],NOW),
                         {'home':ID['homeserver_alternate'],'via':'home statement','sequence':1})
        self.assertEqual(resolve_home(ID['alice'],HOMESERVERS,rejected,NOW)['home'],ID['homeserver_primary'])

    def test_author_answer_matches_slice(self):
        answer=verify_candidates(read('bob-answers','author-dana.json'),advertisement())
        first=verify_slice(E/'headline/bob-slice-1')
        dana={(e['uri'],e['blake3']) for e in first['slice']['entries'] if e['uri'].startswith('pubky://'+ID['dana']+'/')}
        self.assertEqual({(e['uri'],e['blake3']) for e in answer['entries']},dana)

    def test_fixtures_carry_no_private_or_ranking_fields(self):
        forbidden={'favorite','favorites','search','searches','query_log','score','rank','ranking','order',
                   'orders','buyer','customer_address','invoice','payment_request','mnemonic','private_key','seed'}
        for path in E.rglob('*.json'):
            def scan(x):
                if isinstance(x,dict):
                    self.assertFalse(forbidden.intersection(x),path)
                    for v in x.values():scan(v)
                elif isinstance(x,list):
                    for v in x:scan(v)
            try:
                scan(json.loads(path.read_text()))
            except UnicodeDecodeError:
                pass

class Sharing(NoNetwork):
    """Scopes are the published form of a user's share and don't-share choices."""
    def entries(self):
        return verify_slice(E/'headline/bob-slice-2')['slice']['entries']
    def covered(self,scopes):
        return {e['uri'] for e in self.entries() if entry_in_scope(e,scopes)}
    def test_share_a_key(self):
        self.assertEqual(len(self.covered([{'key':ID['dana']}])),7)
    def test_share_a_key_without_tags(self):
        self.assertEqual(self.covered([{'key':ID['dana'],'kinds':['post']}]),{URI['listing'],URI['shirt']})
    def test_share_one_listing(self):
        self.assertEqual(self.covered([{'uri':URI['listing']}]),{URI['listing'],URI['curator_tag'],URI['carol_tag']})
    def test_share_a_label(self):
        self.assertEqual(self.covered([{'label':'great-print'}]),{URI['carol_tag']})
    def test_slice_must_match_choices(self):
        result=verify_slice(E/'headline/bob-slice-2')
        doc=copy.deepcopy(result['slice']);doc['scopes']=[{'uri':URI['shirt']}]
        with self.assertRaises(InvalidSet):check_slice(doc,result['versions'])
    def test_last_read_is_never_shared(self):
        result=verify_slice(E/'headline/bob-slice-2')
        doc=copy.deepcopy(result['slice'])
        doc['entries'].append({'blake3':b3(b'{"timestamp":1}'),'kind':'other','seq':'8',
                               'uri':f'pubky://{ID["dana"]}/pub/pubky.app/last_read'})
        with self.assertRaises(InvalidSet):check_slice(doc,{})

class Advertisements(NoNetwork):
    def test_tampered_advertisement(self):
        raw,sig=signed('bob-provider','provider.json')
        with self.assertRaises(InvalidSet):verify_provider(raw.replace(b'"sequence": 2',b'"sequence": 3'),sig)
    def test_provider_signature_is_not_a_set_signature(self):
        with self.assertRaises(InvalidSet):verify_jws(*signed('bob-provider','provider.json'),'slime-set')
    def test_expired_advertisement(self):
        with self.assertRaises(InvalidSet):verify_provider(*signed('bob-provider','provider.json'),datetime(2026,11,1,tzinfo=timezone.utc))
    def test_grant_must_bind_provider_key(self):
        ad=advertisement()
        alice_grant=json.loads(read('alice-home','home.json'))['grant']
        with self.assertRaises(InvalidSet):check_grant_key(alice_grant,ad['operator'],ad['provider'],NOW)
        with self.assertRaises(InvalidSet):check_grant_key(ad['grant'],ID['alice'],ad['provider'],NOW)
        with self.assertRaises(InvalidSet):check_grant_key(ad['grant'],ad['operator'],ID['carol'],NOW)
    def test_grant_checked_at_issue_time_without_a_clock(self):
        self.assertEqual(verify_provider(*signed('bob-provider','provider.json'))['provider'],ID['bob_provider'])
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
    def test_provider_selection(self):
        ad=advertisement();older=copy.deepcopy(ad);older['sequence']=1
        self.assertEqual(select_providers([older,ad],{'key':ID['dana']},'query',NOW)[0]['sequence'],2)
        self.assertEqual(select_providers([ad],{'key':ID['carol']},'query',NOW),[])
        labelled=copy.deepcopy(ad);labelled['scopes']=[{'label':'great-print'}]
        self.assertEqual(len(select_providers([labelled],{'label':'great-print'},'query',NOW)),1)
    def test_unknown_role_rejected(self):
        raw=json.loads(read('bob-provider','provider.json'));raw['roles'].append('rank')
        with self.assertRaises(InvalidSet):parse(json.dumps(raw).encode(),'provider')

class Grants(NoNetwork):
    def grant(self):
        return advertisement()['grant']
    def test_grant_verifies_offline(self):
        claims=verify_grant(self.grant(),NOW)
        self.assertEqual((claims['iss'],claims['cnf']),(ID['bob'],ID['bob_provider']))
    def test_tampered_grant(self):
        head,body,sig=self.grant().split('.')
        forged=sig[:10]+('B' if sig[10]!='B' else 'C')+sig[11:]
        with self.assertRaises(InvalidSet):verify_grant('.'.join([head,body,forged]),NOW)
        with self.assertRaises(InvalidSet):verify_grant('.'.join([head,body[:-1]+('A' if body[-1]!='A' else 'B'),sig]),NOW)
    def test_grant_header_type(self):
        head,body,sig=self.grant().split('.')
        pop=base64.urlsafe_b64encode(b'{"alg":"EdDSA","typ":"pubky-pop"}').decode().rstrip('=')
        with self.assertRaises(InvalidSet):verify_grant('.'.join([pop,body,sig]),NOW)
    def test_expired_grant(self):
        with self.assertRaises(InvalidSet):verify_grant(self.grant(),AFTER_GRANTS)
    def test_write_capability(self):
        claims=lambda *caps:{'caps':list(caps)}
        self.assertTrue(grant_allows_write(claims('/pub/:rw'),'/pub/slime/'))
        self.assertTrue(grant_allows_write(claims('/pub/slime/:w'),'/pub/slime/'))
        self.assertFalse(grant_allows_write(claims('/pub/slime/:r'),'/pub/slime/'))
        self.assertFalse(grant_allows_write(claims('/pub/pubky.app/:rw'),'/pub/slime/'))
        self.assertFalse(grant_allows_write(claims('pub/:rw','/pub/:x'),'/pub/slime/'))

class Slices(NoNetwork):
    def slice_doc(self):
        result=verify_slice(E/'headline/bob-slice-2')
        return copy.deepcopy(result['slice']),result['versions']
    def test_entry_must_match_bytes(self):
        doc,versions=self.slice_doc()
        doc['entries'][5]['label']='forged'
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_entry_refs_must_match_bytes(self):
        doc,versions=self.slice_doc()
        doc['entries'][3]['refs']=[URI['shirt']]
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_entry_kind_must_match_bytes(self):
        doc,versions=self.slice_doc()
        doc['entries'][2]['kind']='post'
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_entry_outside_scope(self):
        doc,versions=self.slice_doc()
        doc['scopes']=[{'key':ID['carol']}]
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_body_without_entry(self):
        doc,versions=self.slice_doc()
        doc['entries'].pop();doc['through']='6'
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
        self.assertEqual(check_slice(doc,{}),7)
    def test_slice_must_be_signed_by_its_provider(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'s';shutil.copytree(E/'headline/bob-slice-1',dest)
            (dest/'set.jws').unlink()
            with self.assertRaises(InvalidSet):verify_slice(dest)
    def test_other_provider_pin(self):
        with self.assertRaises(InvalidSet):verify_slice(E/'headline/bob-slice-1',expected_provider=ID['carol'])
    def test_expired_provider_grant(self):
        with self.assertRaises(InvalidSet):verify_slice(E/'headline/bob-slice-1',now=AFTER_GRANTS)
    def test_tampered_slice(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'s';shutil.copytree(E/'headline/bob-slice-1',dest)
            p=dest/'slice.json';p.write_bytes(p.read_bytes().replace(b'local-print',b'local-prinz'))
            with self.assertRaises(InvalidSet):verify_slice(dest)
    def test_score_field_rejected(self):
        doc,_=self.slice_doc();doc['entries'][0]['score']=9
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')
    def test_label_only_on_tags(self):
        doc,_=self.slice_doc();doc['entries'][0]['label']='x'
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')
    def test_tag_needs_label(self):
        doc,_=self.slice_doc();del doc['entries'][5]['label']
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')
    def test_listing_kinds_are_not_slime_kinds(self):
        doc,_=self.slice_doc();doc['entries'][3]['kind']='listing'
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')

class Answers(NoNetwork):
    def answer(self,name='refs-listing-tags.json'):
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
        doc=self.answer();doc['query']['after']='7'
        with self.assertRaises(InvalidSet):self.check(doc)
    def test_incomplete_needs_next(self):
        doc=self.answer();doc['complete']=False
        with self.assertRaises(InvalidSet):self.check(doc)
        doc['next']='7'
        self.assertFalse(self.check(doc)['complete'])
        doc['next']='6'
        with self.assertRaises(InvalidSet):self.check(doc)
    def test_outside_advertised_scope(self):
        ad=copy.deepcopy(advertisement());ad['scopes']=[{'key':ID['carol']},{'label':'other'}]
        with self.assertRaises(InvalidSet):self.check(self.answer('author-dana.json'),ad)
    def test_other_provider(self):
        ad=copy.deepcopy(advertisement());ad['provider']=ID['carol']
        with self.assertRaises(InvalidSet):self.check(self.answer(),ad)
    def test_gone_entry(self):
        doc=self.answer();doc['entries']=[{'gone':True,'kind':'tag','seq':'8','uri':URI['carol_tag']}]
        self.assertTrue(self.check(doc)['entries'][0]['gone'])
        doc['entries'][0]['blake3']=b3(b'x')
        with self.assertRaises(InvalidSet):self.check(doc)

class Notices(NoNetwork):
    def test_target_must_be_referenced(self):
        doc=json.loads(read('carol-notice','notice.json'));doc['target']=URI['shirt']
        with self.assertRaises(InvalidSet):verify_notice(json.dumps(doc).encode(),URI['carol_tag'],carol_tag())
    def test_source_hash(self):
        with self.assertRaises(InvalidSet):verify_notice(read('carol-notice','notice.json'),URI['carol_tag'],carol_tag()+b' ')
    def test_bare_key_target(self):
        doc=json.loads(read('carol-notice','notice.json'));doc['target']='pubky://'+ID['dana']+'/'
        self.assertEqual(verify_notice(json.dumps(doc).encode(),URI['carol_tag'],carol_tag())['target'],doc['target'])
    def test_notice_carries_no_body(self):
        doc=json.loads(read('carol-notice','notice.json'));doc['text']='hello'
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'notice')
    def test_listed_provider_accepts(self):
        services=load_services(read('alice-home','services.json'),ID['alice'])
        to_alice=dict(notice(),target='pubky://'+ID['alice']+'/')
        self.assertTrue(accepts_notice(to_alice,ID['bob_provider'],services,None))
        self.assertFalse(accepts_notice(to_alice,ID['other_provider'],services,None))
        with self.assertRaises(InvalidSet):load_services(read('alice-home','services.json'),ID['bob'])
    def test_scope_provider_accepts_only_for_its_scope(self):
        ad=advertisement()
        self.assertTrue(accepts_notice(notice(),ad['provider'],None,ad))
        self.assertFalse(accepts_notice(dict(notice(),target='pubky://'+ID['alice']+'/'),ad['provider'],None,ad))
        quiet=copy.deepcopy(ad);quiet['roles'].remove('notices')
        self.assertFalse(accepts_notice(notice(),ad['provider'],None,quiet))
    def test_proof_of_work(self):
        n=notice()
        check_pow(n,8,NOTICE_HOUR)
        with self.assertRaises(InvalidSet):check_pow(n,8,NOW)
        with self.assertRaises(InvalidSet):check_pow(dict(n,pow='0'*32),8,NOTICE_HOUR)
        with self.assertRaises(InvalidSet):check_pow({k:v for k,v in n.items() if k!='pow'},8,NOTICE_HOUR)

class Flood(NoNetwork):
    """Sybil flood: many fresh keys against one target."""
    def fake(self,i,target=None):
        return {'created_at':f'2026-09-25T10:{i//60%60:02d}:{i%60:02d}Z','source':f'pubky://{ID["carol"]}/pub/pubky.app/tags/{i:026d}',
                'target':target or URI['listing'],'pow':'0'*32}
    def test_reject_not_evict_within_a_target(self):
        queue=NoticeQueue(cold_cap=4,warm_cap=64,global_cap=100000)
        honest=notice()
        self.assertEqual(queue.submit(honest,NOTICE_HOUR),'202')
        results=[queue.submit(self.fake(i),NOTICE_HOUR) for i in range(10000)]
        self.assertEqual(results.count('202'),3)
        self.assertEqual(results.count('503 queue-full'),9997)
        self.assertIn(honest,queue.drain(ID['dana']))
    def test_warm_target_gets_the_larger_cap(self):
        queue=NoticeQueue(cold_cap=4,warm_cap=64,global_cap=100000)
        queue.mark_warm(ID['dana'])
        self.assertEqual([queue.submit(self.fake(i),NOTICE_HOUR) for i in range(70)].count('202'),64)
    def test_global_eviction_is_fair(self):
        queue=NoticeQueue(cold_cap=100,warm_cap=100,global_cap=10)
        other=f'pubky://{ID["alice"]}/'
        for i in range(2):
            queue.submit(self.fake(i,other),NOTICE_HOUR)
        for i in range(100):
            queue.submit(self.fake(i),NOTICE_HOUR)
        self.assertEqual(len(queue),10)
        self.assertEqual(len(queue.queues[ID['alice']]),2)
    def test_pow_floor_and_vouching(self):
        queue=NoticeQueue(cold_cap=4,warm_cap=64,global_cap=100,pow_floor_bits=8)
        self.assertEqual(queue.submit(self.fake(1),NOTICE_HOUR),'400 low-work')
        self.assertEqual(queue.submit(notice(),NOTICE_HOUR),'202')
        self.assertTrue(is_vouched(URI['carol_tag'],{ID['carol']}))
        self.assertEqual(queue.submit(self.fake(2),NOTICE_HOUR,vouched=True),'202')
    def test_requests_view_is_bounded(self):
        view=RequestsView(cap=3)
        for i in range(3):
            view.add(f'peer{i}',f'2026-09-25T10:00:0{i}Z')
        view.view('peer0')
        self.assertTrue(view.add('peer3','2026-09-25T10:00:03Z'))
        self.assertNotIn('peer1',view.rows)
        self.assertIn('peer0',view.rows)
        for peer in list(view.rows):
            view.view(peer)
        self.assertFalse(view.add('peer4','2026-09-25T10:00:04Z'))
        self.assertEqual(len(view.rows),3)

class Failover(NoNetwork):
    def home(self,*path,**kw):
        path=path or ('home.json',)
        args=dict(identity=ID['alice'],homeservers=HOMESERVERS,now=NOW)
        args.update(kw)
        return verify_home(*signed('alice-home',*path),**args)
    def test_valid_statement(self):
        self.assertEqual(self.home()['home'],ID['homeserver_alternate'])
    def test_home_signature_is_not_a_provider_signature(self):
        with self.assertRaises(InvalidSet):verify_jws(*signed('alice-home','home.json'),'slime-provider')
    def test_home_must_be_a_pubky_target(self):
        with self.assertRaises(InvalidSet):self.home('rejected','unenrolled-home.json')
        with self.assertRaises(InvalidSet):self.home(homeservers=[ID['homeserver_primary']])
    def test_signer_must_be_grant_client_key(self):
        with self.assertRaises(InvalidSet):self.home('rejected','wrong-signer-home.json')
    def test_grant_must_allow_writing_slime_paths(self):
        with self.assertRaises(InvalidSet):self.home('rejected','read-only-grant-home.json')
    def test_grant_from_another_identity(self):
        with self.assertRaises(InvalidSet):self.home(identity=ID['bob'])
    def test_expired_grant(self):
        with self.assertRaises(InvalidSet):self.home(now=AFTER_GRANTS)
    def test_stale_statement(self):
        with self.assertRaises(InvalidSet):self.home(last_sequence=1)
        self.assertEqual(self.home(last_sequence=0)['sequence'],1)
    def test_no_homeserver(self):
        with self.assertRaises(InvalidSet):resolve_home(ID['alice'],[],[signed('alice-home','home.json')],NOW)

class Dependencies(NoNetwork):
    def index(self,skip=()):
        index=LocalIndex()
        for (origin,digest),raw in verify_slice(E/'headline/bob-slice-1')['versions'].items():
            if origin not in skip:index.admit(origin,raw,digest)
        return index
    def test_four_states(self):
        index=self.index(skip={URI['blob'],URI['dana_profile']})
        self.assertEqual(dict(index.closure(URI['listing'])),
                         {URI['file']:'retained',URI['blob']:'missing',URI['dana_profile']:'missing'})
        states=dict(index.closure(URI['listing'],holders={URI['blob']},withheld={URI['dana_profile']}))
        self.assertEqual((states[URI['blob']],states[URI['dana_profile']]),('fetchable','withheld'))
    def test_chain_stops_at_a_gap(self):
        index=self.index(skip={URI['file']})
        self.assertEqual(dict(index.closure(URI['listing'])),{URI['file']:'missing',URI['dana_profile']:'retained'})
    def test_wrong_bytes_rejected(self):
        with self.assertRaises(InvalidSet):LocalIndex().admit(URI['carol_tag'],carol_tag(),b3(b'x'))
    def test_lying_candidate_rejected(self):
        entry=json.loads(read('bob-answers','refs-listing-tags.json'))['entries'][0]
        entry['refs']=[URI['shirt']]
        with self.assertRaises(InvalidSet):LocalIndex().admit(entry['uri'],carol_tag(),entry['blake3'],entry)
    def test_import_order_independent(self):
        a,b=LocalIndex(),LocalIndex()
        first,second=verify_slice(E/'headline/bob-slice-1'),verify_slice(E/'headline/bob-slice-2')
        a.admit_set(first);a.admit_set(second);b.admit_set(second);b.admit_set(first)
        for op,args in [('author',{'key':ID['dana']}),('label',{'label':'great-print'}),('refs',{'uri':URI['listing']})]:
            self.assertEqual(a.query(op,**args),b.query(op,**args))
    def test_domain_primitive_on_a_tag(self):
        index=LocalIndex()
        index.admit_set(verify_set(E/'github-signed'))
        self.assertEqual(index.query('domain',host='github.com'),sorted([URI['author_tag'],URI['author_profile']]))

if __name__=='__main__':unittest.main()
