"""The headline acceptance test's data path, run offline against the fixtures.

Covers what files can show: signed indexer answers, static slice import into a local index with
every copy checked against its author signature, rejection of a forged copy, conflicts among
author-signed versions only, dependency states, grants, and home statements. It does not show that
an App boots offline, that an indexer fails over, that Ring signs a grant, or that a homeserver
accepts a write.
"""
from pathlib import Path
from datetime import datetime, timezone
import base64,copy,json,shutil,socket,tempfile,unittest
from check_sets import (InvalidSet,LocalIndex,b3,check_entries,check_grant_key,check_slice,current_versions,
                        entry_in_scope,grant_allows_write,load_services,parse,resolve_home,verify_answer,
                        verify_grant,verify_home,verify_jws,verify_set,verify_slice)

E=Path(__file__).resolve().parent
H=E/'headline'
EXPECTED=json.loads((E/'expected.json').read_text())
ID=EXPECTED['identities']
URI=EXPECTED['uris']
HASH=EXPECTED['hashes']
NOW=datetime(2026,9,25,12,30,0,tzinfo=timezone.utc)
AFTER_GRANTS=datetime(2028,9,22,tzinfo=timezone.utc)
# The _pubky targets of Alice's PKARR packet, in priority order, as the PKARR library resolves them.
HOMESERVERS=[ID['homeserver_primary'],ID['homeserver_alternate']]

def read(*parts):
    return (H.joinpath(*parts)).read_bytes()

def signed(*parts):
    return read(*parts),read(*parts[:-1],parts[-1][:-len('.json')]+'.jws').decode()

def answer(name):
    return verify_answer(*signed('indexer-answers',f'{name}.json'),ID['indexer_operator'],NOW)

def forged():
    folder=H/'forged-listing'
    return (folder/'record.json').read_bytes(),(folder/'record.sig').read_text().strip(),(folder/'grant.jws').read_text().strip()

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
        # Nexus is gone; Alice's app asks a second indexer, which Synonym does not run.
        dana=answer('author-dana')
        self.assertEqual({e['uri'] for e in dana['entries'] if e['kind']=='post'},{URI['listing'],URI['shirt']})
        # Dana's homeserver is dark. Alice imports Bob's static slice; every copy carries its author signature.
        first=verify_slice(E/'headline/bob-slice-1')
        self.assertEqual(first['operator'],ID['bob'])
        index=LocalIndex()
        self.assertEqual(index.admit_set(first),6)
        self.assertEqual(index.query('author',key=ID['dana'],kind='post'),sorted([URI['listing'],URI['shirt']]))
        self.assertEqual(index.query('refs',uri=URI['listing'],kind='tag'),[URI['curator_tag']])
        self.assertEqual(index.closure(URI['listing']),sorted([(URI['blob'],'retained'),(URI['dana_profile'],'retained'),(URI['file'],'retained')]))
        # A forged listing with another price is rejected, not shown as a version.
        raw,sig,grant=forged()
        with self.assertRaises(InvalidSet):index.admit(URI['listing'],raw,sig,grant)
        self.assertEqual(index.query('author',key=ID['dana'],kind='post'),sorted([URI['listing'],URI['shirt']]))
        # Carol tags the listing; Alice finds the tag through the indexer's label search.
        [tag]=answer('label-great-print')['entries']
        body=(E/'headline/bob-slice-2/records'/URI['carol_tag'][len('pubky://'):]).read_bytes()
        self.assertTrue(index.admit(tag['uri'],body,tag['sig'],tag['grant'],tag))
        self.assertEqual(index.query('refs',uri=URI['listing'],kind='tag'),sorted([URI['curator_tag'],URI['carol_tag']]))
        # Bob's next snapshot carries the same tag; importing it adds nothing twice.
        second=verify_slice(E/'headline/bob-slice-2')
        self.assertEqual(second['previous'],first['id'])
        self.assertEqual(index.admit_set(second),0)
        # Alice's primary refuses her writes and serves stale reads; her home statement names the alternate for edits.
        home=signed('alice-home','home.json')
        rejected=[signed('alice-home','rejected',n) for n in ('unenrolled-home.json','wrong-signer-home.json','read-only-grant-home.json')]
        self.assertEqual(resolve_home(ID['alice'],HOMESERVERS,rejected+[home],NOW),
                         {'home':ID['homeserver_alternate'],'via':'home statement','sequence':1})
        self.assertEqual(resolve_home(ID['alice'],HOMESERVERS,rejected,NOW)['home'],ID['homeserver_primary'])

    def test_answer_matches_slice(self):
        dana={(e['uri'],e['blake3']) for e in answer('author-dana')['entries']}
        first=verify_slice(E/'headline/bob-slice-1')
        self.assertEqual({(e['uri'],e['blake3']) for e in first['slice']['entries'] if e['uri'].startswith('pubky://'+ID['dana']+'/')},dana)

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

class Conflicts(NoNetwork):
    """Only author-signed versions count. Unsigned or badly signed copies never reach the merge."""
    def test_unsigned_copy_rejected(self):
        raw,_,_=forged()
        with self.assertRaises(InvalidSet):LocalIndex().admit(URI['listing'],raw)
    def test_two_signed_versions_conflict_until_the_stream_decides(self):
        heads=current_versions({},{URI['listing']:{HASH['listing'],HASH['listing_withdrawn']}})
        self.assertEqual(len(heads[URI['listing']]),2)
    def test_origin_reads_need_no_signature(self):
        raw,_,_=forged()
        self.assertTrue(LocalIndex().admit(URI['listing'],raw,from_origin=True))

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
        doc=copy.deepcopy(verify_slice(E/'headline/bob-slice-2')['slice'])
        extra=dict(doc['entries'][0],seq='8',uri=f'pubky://{ID["dana"]}/pub/pubky.app/last_read')
        doc['entries'].append(extra)
        with self.assertRaises(InvalidSet):check_slice(doc,{})

class Slices(NoNetwork):
    def slice_doc(self):
        result=verify_slice(E/'headline/bob-slice-2')
        return copy.deepcopy(result['slice']),result['versions']
    def test_entry_must_match_bytes(self):
        doc,versions=self.slice_doc();doc['entries'][5]['label']='forged'
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_entry_signature_must_match_entry(self):
        doc,_=self.slice_doc();doc['entries'][3]['sig']=doc['entries'][4]['sig']
        with self.assertRaises(InvalidSet):check_slice(doc,{})
    def test_entry_without_signature_rejected(self):
        doc,_=self.slice_doc();del doc['entries'][3]['sig']
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')
    def test_entry_outside_scope(self):
        doc,versions=self.slice_doc();doc['scopes']=[{'key':ID['carol']}]
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_body_without_entry(self):
        doc,versions=self.slice_doc();doc['entries'].pop();doc['through']='6'
        with self.assertRaises(InvalidSet):check_slice(doc,versions)
    def test_seq_order(self):
        doc,_=self.slice_doc();doc['entries'][0],doc['entries'][1]=doc['entries'][1],doc['entries'][0]
        with self.assertRaises(InvalidSet):check_entries(doc['entries'])
    def test_entries_only_slice_is_allowed(self):
        doc,_=self.slice_doc()
        self.assertEqual(check_slice(doc,{}),7)
    def test_slice_must_be_signed_by_its_publisher(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'s';shutil.copytree(E/'headline/bob-slice-1',dest)
            (dest/'set.jws').unlink()
            with self.assertRaises(InvalidSet):verify_slice(dest)
    def test_other_publisher_pin(self):
        with self.assertRaises(InvalidSet):verify_slice(E/'headline/bob-slice-1',expected_publisher=ID['carol'])
    def test_expired_publisher_grant(self):
        with self.assertRaises(InvalidSet):verify_slice(E/'headline/bob-slice-1',now=AFTER_GRANTS)
    def test_score_field_rejected(self):
        doc,_=self.slice_doc();doc['entries'][0]['score']=9
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')
    def test_listing_kinds_are_not_slime_kinds(self):
        doc,_=self.slice_doc();doc['entries'][3]['kind']='listing'
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'slice')

class Answers(NoNetwork):
    def raw(self,name='label-great-print'):
        return signed('indexer-answers',f'{name}.json')
    def test_tampered_answer(self):
        body,sig=self.raw()
        with self.assertRaises(InvalidSet):verify_answer(body.replace(b'"complete": true',b'"complete": false'),sig)
    def test_answer_signature_type(self):
        with self.assertRaises(InvalidSet):verify_jws(*self.raw(),'slime-set')
    def test_unconfigured_operator(self):
        with self.assertRaises(InvalidSet):verify_answer(*self.raw(),ID['bob'],NOW)
    def test_expired_indexer_grant(self):
        with self.assertRaises(InvalidSet):verify_answer(*self.raw(),now=AFTER_GRANTS)
    def test_rank_field_rejected(self):
        doc=json.loads(self.raw()[0]);doc['entries'][0]['rank']=1
        with self.assertRaises(InvalidSet):parse(json.dumps(doc).encode(),'candidates')
    def test_entries_carry_author_signatures(self):
        for e in answer('author-dana')['entries']:
            self.assertIn('sig',e)

class Grants(NoNetwork):
    def grant(self):
        return json.loads(read('bob-slice-1','slice.json'))['grant']
    def test_grant_verifies_offline(self):
        claims=verify_grant(self.grant(),NOW)
        self.assertEqual((claims['iss'],claims['cnf']),(ID['bob'],ID['bob_publisher']))
    def test_tampered_grant(self):
        head,body,sig=self.grant().split('.')
        forged_sig=sig[:10]+('B' if sig[10]!='B' else 'C')+sig[11:]
        with self.assertRaises(InvalidSet):verify_grant('.'.join([head,body,forged_sig]),NOW)
    def test_grant_header_type(self):
        head,body,sig=self.grant().split('.')
        pop=base64.urlsafe_b64encode(b'{"alg":"EdDSA","typ":"pubky-pop"}').decode().rstrip('=')
        with self.assertRaises(InvalidSet):verify_grant('.'.join([pop,body,sig]),NOW)
    def test_grant_must_bind_key(self):
        with self.assertRaises(InvalidSet):check_grant_key(self.grant(),ID['alice'],ID['bob_publisher'],NOW)
        with self.assertRaises(InvalidSet):check_grant_key(self.grant(),ID['bob'],ID['carol'],NOW)
    def test_write_capability(self):
        claims=lambda *caps:{'caps':list(caps)}
        self.assertTrue(grant_allows_write(claims('/pub/:rw'),'/pub/slime/'))
        self.assertFalse(grant_allows_write(claims('/pub/slime/:r'),'/pub/slime/'))
        self.assertFalse(grant_allows_write(claims('/pub/pubky.app/:rw'),'/pub/slime/'))
        self.assertTrue(grant_allows_write(claims('/pub/pubky.app/:rw'),'/pub/pubky.app/posts/X'))

class Failover(NoNetwork):
    def home(self,*path,**kw):
        path=path or ('home.json',)
        args=dict(identity=ID['alice'],homeservers=HOMESERVERS,now=NOW)
        args.update(kw)
        return verify_home(*signed('alice-home',*path),**args)
    def test_valid_statement(self):
        self.assertEqual(self.home()['home'],ID['homeserver_alternate'])
    def test_home_must_be_a_pubky_target(self):
        with self.assertRaises(InvalidSet):self.home('rejected','unenrolled-home.json')
    def test_signer_must_be_grant_client_key(self):
        with self.assertRaises(InvalidSet):self.home('rejected','wrong-signer-home.json')
    def test_grant_must_allow_writing_slime_paths(self):
        with self.assertRaises(InvalidSet):self.home('rejected','read-only-grant-home.json')
    def test_expired_grant(self):
        with self.assertRaises(InvalidSet):self.home(now=AFTER_GRANTS)
    def test_stale_statement(self):
        with self.assertRaises(InvalidSet):self.home(last_sequence=1)
    def test_services_name_mirrors(self):
        services=load_services(read('alice-home','services.json'),ID['alice'])
        self.assertEqual(services['mirrors'],[ID['mirror']])
        with self.assertRaises(InvalidSet):load_services(read('alice-home','services.json'),ID['bob'])

class Dependencies(NoNetwork):
    def index(self,skip=()):
        index=LocalIndex()
        result=verify_slice(E/'headline/bob-slice-1')
        for (origin,digest),raw in result['versions'].items():
            if origin not in skip:index.admit(origin,raw,*result['sigs'][(origin,digest)])
        return index
    def test_four_states(self):
        index=self.index(skip={URI['blob'],URI['dana_profile']})
        self.assertEqual(dict(index.closure(URI['listing'])),{URI['file']:'retained',URI['blob']:'missing',URI['dana_profile']:'missing'})
        states=dict(index.closure(URI['listing'],holders={URI['blob']},withheld={URI['dana_profile']}))
        self.assertEqual((states[URI['blob']],states[URI['dana_profile']]),('fetchable','withheld'))
    def test_chain_stops_at_a_gap(self):
        index=self.index(skip={URI['file']})
        self.assertEqual(dict(index.closure(URI['listing'])),{URI['file']:'missing',URI['dana_profile']:'retained'})
    def test_import_order_independent(self):
        a,b=LocalIndex(),LocalIndex()
        first,second=verify_slice(E/'headline/bob-slice-1'),verify_slice(E/'headline/bob-slice-2')
        a.admit_set(first);a.admit_set(second);b.admit_set(second);b.admit_set(first)
        for op,args in [('author',{'key':ID['dana']}),('label',{'label':'great-print'}),('refs',{'uri':URI['listing']})]:
            self.assertEqual(a.query(op,**args),b.query(op,**args))
    def test_domain_primitive(self):
        index=LocalIndex()
        index.admit_set(verify_set(E/'github-signed'))
        self.assertEqual(index.query('domain',host='github.com'),sorted([URI['author_tag'],URI['author_profile']]))

if __name__=='__main__':unittest.main()
