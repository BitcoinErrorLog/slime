"""Selected executable conformance examples, not the full acceptance matrix."""
from pathlib import Path
import contextlib,copy,hashlib,json,shutil,tempfile,unittest,zipfile
from check_sets import InvalidSet,parse,verify_set,verify_signature,merge_heads,key_decode,key_encode,safe_path
E=Path(__file__).resolve().parent
EXPECTED=json.loads((E/'expected.json').read_text())

@contextlib.contextmanager
def fixture(name='github-signed'):
    with tempfile.TemporaryDirectory() as d:
        dest=Path(d)/'set';shutil.copytree(E/name,dest);yield dest

def member(d):
    inv=json.loads((d/'set.json').read_text())
    return d/next(f['path'] for f in inv['files'] if 'origin' in f)

class Conformance(unittest.TestCase):
    def test_all_inventoried_sets(self):
        for name,want in EXPECTED['sets'].items():
            with self.subTest(name=name):self.assertEqual(verify_set(E/name)['id'],want)
    def test_plain_set_has_no_required_metadata(self):
        self.assertTrue((E/'github-plain/README.md').exists())
        self.assertFalse((E/'github-plain/set.json').exists())
    def test_unsigned_inventory_allowed(self):
        self.assertIsNone(verify_set(E/'github-inventoried')['signer'])
    def test_expected_exporter(self):
        self.assertEqual(verify_set(E/'shops-public',EXPECTED['identities']['curator'])['signer'],EXPECTED['identities']['curator'])
    def test_signed_source_cannot_downgrade_to_unsigned(self):
        with self.assertRaises(InvalidSet):verify_set(E/'github-inventoried',EXPECTED['identities']['curator'])
    def test_wrong_exporter_pin(self):
        with self.assertRaises(InvalidSet):verify_set(E/'shops-public',EXPECTED['identities']['seller'])
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
        # Only our own trusted fixture ZIP is extracted in this test.
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); archive=td/'set.zip'; out=td/'renamed'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for p in (E/'github-signed').rglob('*'):
                    if p.is_file():z.write(p,p.relative_to(E/'github-signed'))
            with zipfile.ZipFile(archive) as z:z.extractall(out)
            self.assertEqual(verify_set(out)['id'],EXPECTED['sets']['github-signed'])
    def test_duplicate_json_keys(self):
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
        for key in EXPECTED['identities'].values():self.assertEqual(key_encode(key_decode(key)),key)
    def test_signature_role_confusion(self):
        d=E/'github-signed'
        with self.assertRaises(InvalidSet):verify_signature((d/'set.json').read_bytes(),(d/'set.sig.json').read_bytes(),'record')
    def test_bad_signature(self):
        with fixture() as d:
            s=json.loads((d/'set.sig.json').read_text());s['signature']='A'*86;(d/'set.sig.json').write_text(json.dumps(s))
            with self.assertRaises(InvalidSet):verify_set(d)
    def test_author_and_curator_are_distinct(self):
        r=verify_set(E/'shops-public')
        self.assertEqual(r['signer'],EXPECTED['identities']['curator'])
        self.assertIn(EXPECTED['listing_origin'],{s['origin'] for s in r['statements'].values()})
    def test_delete_resists_ancestor_replay(self):
        a,b=verify_set(E/'github-signed'),verify_set(E/'github-history')
        want=[(EXPECTED['tag_statements']['delete'],'delete')]
        self.assertEqual(merge_heads([b,a,a])[EXPECTED['tag_origin']],want)
    def test_concurrent_heads_retained(self):
        heads=merge_heads([verify_set(E/'github-fork')])[EXPECTED['tag_origin']]
        self.assertEqual(len(heads),2)
    def test_author_join(self):
        heads=merge_heads([verify_set(E/'github-fork'),verify_set(E/'github-joined')])[EXPECTED['tag_origin']]
        self.assertEqual(heads,[(EXPECTED['tag_statements']['joined'],'put')])
    def test_import_order_independent_heads(self):
        a,b=verify_set(E/'github-signed'),verify_set(E/'github-history')
        self.assertEqual(merge_heads([a,b]),merge_heads([b,a]))
    def test_catalog_withdrawal_survives_old_copy(self):
        a,b=verify_set(E/'shops-public'),verify_set(E/'shops-withdrawn')
        heads=merge_heads([b,a])[EXPECTED['listing_origin']]
        self.assertEqual(heads,[(EXPECTED['listing_statements']['withdrawn'],'put')])
        statement=b['statements'][heads[0][0]]
        body=json.loads(b['versions'][(statement['origin'],statement['content_sha256'])])
        self.assertEqual(body['availability'],'withdrawn')
    def test_duplicate_evidence_is_not_extra_stock(self):
        a=verify_set(E/'shops-public'); union={}
        for _ in range(10):union.update(a['versions'])
        listing_bodies=[b for (origin,_),b in union.items() if origin==EXPECTED['listing_origin']]
        self.assertEqual(len(listing_bodies),1)
        self.assertEqual(json.loads(listing_bodies[0])['quantity'],1)
    def test_fixture_public_catalog_no_private_fields(self):
        # Static fixture inspection, NOT an operational export-allowlist test.
        forbidden={'order','orders','buyer','customer_address','invoice','payment_request','mnemonic','private_key'}
        for path in (E/'shops-public').rglob('*.json'):
            def scan(x):
                if isinstance(x,dict):
                    self.assertFalse(forbidden.intersection(x))
                    for v in x.values():scan(v)
                elif isinstance(x,list):
                    for v in x:scan(v)
            scan(json.loads(path.read_text()))

if __name__=='__main__':unittest.main()
