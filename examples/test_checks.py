"""Folders, signatures, hostile input, pubky.app record adapters, and merges over event streams."""
from pathlib import Path
import contextlib,json,shutil,tempfile,unittest,zipfile
from check_sets import (InvalidSet,b3,current_versions,derive,dependencies,hash_id,key_decode,key_encode,
                        parse,parse_events,safe_path,text_refs,timestamp_id_micros,verify_jws,verify_set)

E=Path(__file__).resolve().parent
EXPECTED=json.loads((E/'expected.json').read_text())
ID=EXPECTED['identities']
URI=EXPECTED['uris']
H=EXPECTED['hashes']

@contextlib.contextmanager
def fixture(name='github-signed'):
    with tempfile.TemporaryDirectory() as d:
        dest=Path(d)/'set';shutil.copytree(E/name,dest);yield dest

def member(d):
    inv=json.loads((d/'set.json').read_text())
    return d/next(f['path'] for f in inv['files'] if 'origin' in f)

def record(folder,uri):
    return (E/folder/'records'/uri[len('pubky://'):]).read_bytes()

class Folders(unittest.TestCase):
    def test_inventoried_sets(self):
        for name,want in EXPECTED['sets'].items():
            with self.subTest(name=name):self.assertEqual(verify_set(E/name)['id'],want)
    def test_plain_set_has_no_required_metadata(self):
        self.assertTrue((E/'github-plain/README.md').exists())
        self.assertFalse((E/'github-plain/set.json').exists())
    def test_unsigned_inventory_allowed(self):
        self.assertIsNone(verify_set(E/'github-inventoried')['signer'])
    def test_expected_exporter(self):
        self.assertEqual(verify_set(E/'shops-public',ID['curator'])['signer'],ID['curator'])
    def test_signed_source_cannot_downgrade_to_unsigned(self):
        with self.assertRaises(InvalidSet):verify_set(E/'github-inventoried',ID['curator'])
    def test_wrong_exporter_pin(self):
        with self.assertRaises(InvalidSet):verify_set(E/'shops-public',ID['dana'])
    def test_tamper_record(self):
        with fixture() as d:
            p=member(d);p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(InvalidSet):verify_set(d)
    def test_tamper_readme(self):
        with fixture() as d:
            (d/'README.md').write_text('changed')
            with self.assertRaises(InvalidSet):verify_set(d)
    def test_missing_member(self):
        with fixture() as d:
            member(d).unlink()
            with self.assertRaises(InvalidSet):verify_set(d)
    def test_extra_member(self):
        with fixture() as d:
            (d/'extra.txt').write_text('unlisted')
            with self.assertRaises(InvalidSet):verify_set(d)
    def test_inventory_reserialization_breaks_signature(self):
        with fixture() as d:
            inv=json.loads((d/'set.json').read_text());(d/'set.json').write_text(json.dumps(inv))
            with self.assertRaises(InvalidSet):verify_set(d)
    def test_repack_invariance(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); archive=td/'set.zip'; out=td/'renamed'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for p in (E/'github-signed').rglob('*'):
                    if p.is_file():z.write(p,p.relative_to(E/'github-signed'))
            with zipfile.ZipFile(archive) as z:z.extractall(out)
            self.assertEqual(verify_set(out)['id'],EXPECTED['sets']['github-signed'])
    def test_origin_must_match_path(self):
        with fixture() as d:
            inv=json.loads((d/'set.json').read_text())
            for f in inv['files']:
                if 'origin' in f:f['origin']=f['origin'].replace('tags','posts')
            (d/'set.json').write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n');(d/'set.jws').unlink()
            with self.assertRaises(InvalidSet):verify_set(d)

class Json(unittest.TestCase):
    def test_duplicate_keys(self):
        with self.assertRaises(InvalidSet):parse(b'{"format":"slime-set/1","format":"slime-set/1","files":[]}','set')
    def test_bom(self):
        with self.assertRaises(InvalidSet):parse(b'\xef\xbb\xbf{}','set')
    def test_unknown_control_fields(self):
        with self.assertRaises(InvalidSet):parse(b'{"format":"slime-set/1","files":[],"run":"command"}','set')
    def test_unsafe_paths(self):
        for name in ['../x','/x','a//b','a/CON','AUX.txt','x\\y','a/%2e%2e/b','a/.','a/b.']:
            with self.subTest(name=name),self.assertRaises(InvalidSet):safe_path(name)
    def test_symlink(self):
        with fixture() as d:
            (d/'alias').symlink_to(d/'README.md')
            with self.assertRaises(InvalidSet):verify_set(d)
    def test_key_codec_roundtrip(self):
        for key in ID.values():self.assertEqual(key_encode(key_decode(key)),key)

class Signatures(unittest.TestCase):
    def jws(self):
        return (E/'github-signed/set.jws').read_text()
    def test_type_confusion(self):
        with self.assertRaises(InvalidSet):verify_jws((E/'github-signed/set.json').read_bytes(),self.jws(),'slime-home')
    def test_bad_signature(self):
        head,_,sig=self.jws().strip().split('.')
        forged=sig[:10]+('B' if sig[10]!='B' else 'C')+sig[11:]
        with self.assertRaises(InvalidSet):verify_jws((E/'github-signed/set.json').read_bytes(),head+'..'+forged,'slime-set')
    def test_attached_payload_rejected(self):
        head,_,sig=self.jws().strip().split('.')
        with self.assertRaises(InvalidSet):verify_jws(b'x',head+'.eA.'+sig,'slime-set')
    def test_signature_binds_exact_bytes(self):
        with self.assertRaises(InvalidSet):verify_jws((E/'github-signed/set.json').read_bytes()+b'\n',self.jws(),'slime-set')

class AppRecords(unittest.TestCase):
    def test_tag(self):
        d=derive(URI['author_tag'],record('github-signed',URI['author_tag']))
        self.assertEqual((d['kind'],d['label']),('tag','rust'))
    def test_tag_id_must_match(self):
        raw=record('github-signed',URI['author_tag'])
        with self.assertRaises(InvalidSet):derive(URI['author_tag'][:-1]+'0',raw)
    def test_tag_label_rules(self):
        base=URI['author_tag'].rsplit('/',1)[0]+'/'
        for label in ['Rust','a'*21,'a:b','two words']:
            body=json.dumps({'uri':'https://example.org','label':label,'created_at':1}).encode()
            with self.subTest(label=label),self.assertRaises(InvalidSet):
                derive(base+hash_id(f'https://example.org:{label}'.encode()),body)
    def test_post_reaches_blob_through_file(self):
        post=derive(URI['listing'],record('shops-public',URI['listing']))
        self.assertIn(URI['file'],post['refs'])
        self.assertIn('https://dana-prints.example/harbor',post['refs'])
        self.assertEqual(derive(URI['file'],record('shops-public',URI['file']))['refs'],[URI['blob']])
        self.assertEqual(derive(URI['blob'],record('shops-public',URI['blob'])),{'kind':'blob'})
    def test_profile_is_a_dependency(self):
        self.assertIn(URI['dana_profile'],dependencies(URI['listing'],record('shops-public',URI['listing'])))
        self.assertNotIn(URI['dana_profile'],dependencies(URI['dana_profile'],record('shops-public',URI['dana_profile'])))
    def test_blob_id_must_match_bytes(self):
        with self.assertRaises(InvalidSet):derive(URI['blob'],b'other bytes')
    def test_timestamp_ids(self):
        self.assertEqual(timestamp_id_micros(URI['listing'].rsplit('/',1)[1]),1790164802000000)
        for bad in ['0000000000000','ABC','0000000000001']:
            with self.subTest(bad=bad),self.assertRaises(InvalidSet):timestamp_id_micros(bad)
    def test_follow_bookmark_mute(self):
        dana=ID['dana']
        self.assertEqual(derive(f'pubky://{ID["alice"]}/pub/pubky.app/follows/{dana}',b'{"created_at":1}'),
                         {'kind':'follow','refs':[f'pubky://{dana}/']})
        self.assertEqual(derive(f'pubky://{ID["alice"]}/pub/pubky.app/mutes/{dana}',b'{"created_at":1}')['kind'],'mute')
        body=json.dumps({'uri':URI['listing'],'created_at':1}).encode()
        uri=f'pubky://{ID["alice"]}/pub/pubky.app/bookmarks/'+hash_id(URI['listing'].encode())
        self.assertEqual(derive(uri,body),{'kind':'bookmark','refs':[URI['listing']]})
        with self.assertRaises(InvalidSet):derive(uri[:-1]+'0',body)
    def test_last_read_is_its_own_kind(self):
        self.assertEqual(derive(f'pubky://{ID["alice"]}/pub/pubky.app/last_read',b'{"timestamp":1}'),{'kind':'last_read'})
    def test_text_links(self):
        self.assertEqual(text_refs('See https://a.example/x. And (https://b.example/y), pubky://'+ID['dana']+' too!'),
                         {'https://a.example/x','https://b.example/y','pubky://'+ID['dana']+'/'})
    def test_unknown_types_are_indexed_by_their_references(self):
        dana='pubky://'+ID['dana']
        body=json.dumps({'a':{'b':[URI['listing'],dana,'https://example.org/x',dana+'/priv/secret','plain']}}).encode()
        self.assertEqual(derive(dana+'/pub/some.app/items/1',body),
                         {'kind':'other','refs':sorted([URI['listing'],dana+'/','https://example.org/x'])})
        self.assertEqual(derive(dana+'/pub/some.app/items/2',b'\x00binary'),{'kind':'other'})

class Merge(unittest.TestCase):
    """Native identity and homeserver event streams decide the current version."""
    def log(self):
        return parse_events((E/'shops-events/events.txt').read_text())
    def test_newer_version_beats_older_copy(self):
        heads=current_versions({ID['homeserver_primary']:self.log()},{URI['listing']:{H['listing']}})
        self.assertEqual(heads[URI['listing']],[('put',H['listing_withdrawn'])])
        body=(E/'shops-events/records'/URI['listing'][len('pubky://'):]).read_bytes()
        self.assertEqual(b3(body),H['listing_withdrawn'])
    def test_delete_resists_replay(self):
        heads=current_versions({ID['homeserver_primary']:self.log()},{URI['shirt']:{H['shirt']}})
        self.assertEqual(heads[URI['shirt']],[('del',)])
    def test_copies_alone_keep_every_head(self):
        heads=current_versions({},{URI['listing']:{H['listing'],H['listing_withdrawn']}})
        self.assertEqual(len(heads[URI['listing']]),2)
    def alternate(self,hash_):
        return parse_events(f'event: PUT\ndata: {URI["listing"]}\ndata: cursor: 5\ndata: content_hash: {hash_}\n\n'
                            f'event: PUT\ndata: {URI["listing"][:-2]}ZZ\ndata: cursor: 6\ndata: content_hash: {hash_}\n')
    def test_homeservers_that_disagree_keep_both_until_a_home_statement_decides(self):
        logs={ID['homeserver_primary']:self.log(),ID['homeserver_alternate']:self.alternate(H['listing'])}
        self.assertEqual(len(current_versions(logs,{})[URI['listing']]),2)
        decided=current_versions(logs,{},ID['homeserver_alternate'])
        self.assertEqual(decided[URI['listing']],[('put',H['listing'])])
    def test_new_records_are_the_union_of_enrolled_homeservers(self):
        logs={ID['homeserver_primary']:self.log(),ID['homeserver_alternate']:self.alternate(H['listing'])}
        heads=current_versions(logs,{},ID['homeserver_primary'])
        self.assertIn(URI['listing'][:-2]+'ZZ',heads)
    def test_order_independent(self):
        a=current_versions({ID['homeserver_primary']:self.log()},{URI['listing']:{H['listing'],H['shirt']}})
        b=current_versions({ID['homeserver_primary']:self.log()},{URI['listing']:{H['shirt'],H['listing']}})
        self.assertEqual(a,b)
    def test_cursors_must_increase(self):
        text=(E/'shops-events/events.txt').read_text().replace('cursor: 102','cursor: 999')
        with self.assertRaises(InvalidSet):parse_events(text)
    def test_malformed_events(self):
        with self.assertRaises(InvalidSet):parse_events('event: PATCH\ndata: x\ndata: cursor: 1\n')

if __name__=='__main__':unittest.main()
