import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from agent.tools import Tools
from mcp_network import calculate,search_papers,search_web,current_time,public_addresses,PublicConnection


class DocumentsAndResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.tools=Tools(self.root,self.root/'state')
    def tearDown(self):self.temp.cleanup()

    def test_docx_read_returns_text_and_pagination(self):
        with ZipFile(self.root/'paper.docx','w') as archive:
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>First paragraph</w:t></w:r></w:p><w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body></w:document>')
        result=self.tools.read('paper.docx',limit=1)
        self.assertIn('First paragraph',result['text']);self.assertEqual(result['remaining_lines'],1)
        self.assertIn('Second paragraph',self.tools.read('paper.docx',offset=2)['text'])

    def test_pdf_text_extraction_and_blank_scans_are_distinguished(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(width=300,height=400)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 350 Td (Research text example) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        with (self.root/'paper.pdf').open('wb') as handle:writer.write(handle)
        result=self.tools.read('paper.pdf');self.assertIn('Research text example',result['text']);self.assertEqual(result['pages'],1)
        blank=PdfWriter();blank.add_blank_page(width=200,height=200)
        with (self.root/'blank.pdf').open('wb') as handle:blank.write(handle)
        with self.assertRaisesRegex(ValueError,'OCR'):self.tools.read('blank.pdf')

    def test_crossref_preserves_real_doi_and_marks_metadata_only(self):
        body={'message':{'items':[{'DOI':'10.1000/example','title':['A &amp; B'],'author':[{'given':'Ada','family':'Lovelace'}],'published':{'date-parts':[[2024,5]]},'type':'journal-article','container-title':['Journal']} ]}}
        with patch('mcp_network.fetch',return_value=(json.dumps(body),'application/json','url')) as request:
            result=search_papers('topic',year_from=2022,limit=1)
        paper=result['papers'][0];self.assertEqual(paper['title'],'A & B');self.assertEqual(paper['url'],'https://doi.org/10.1000/example');self.assertFalse(paper['full_text_read']);self.assertIn('from-pub-date',request.call_args[0][0])

    def test_arxiv_is_labelled_preprint_with_original_link(self):
        xml='<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2401.12345</id><title>Example</title><published>2024-01-20T00:00:00Z</published><author><name>Author</name></author><summary>Abstract.</summary></entry></feed>'
        with patch('mcp_network.fetch',return_value=(xml,'application/atom+xml','url')):result=search_papers('topic',source='arxiv')
        self.assertEqual(result['papers'][0]['type'],'preprint');self.assertTrue(result['papers'][0]['url'].startswith('https://arxiv.org/abs/'))

    def test_paper_query_limits_and_year_bounds(self):
        for kwargs in ({'query':''},{'query':'x','limit':100},{'query':'x','year_from':2035},{'query':'x','year_from':2025,'year_to':2020}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):search_papers(**kwargs)

    def test_search_results_have_source_links_without_duplicate_results(self):
        rss='<rss><channel><item><title>Official docs</title><link>https://example.org/docs</link><description>Public result</description></item><item><title>Duplicate</title><link>https://example.org/docs</link></item></channel></rss>'
        with patch('mcp_network.DDGS') as search,patch('mcp_network.fetch',return_value=(rss,'application/rss+xml','url')):
            search.return_value.text.return_value=[]
            result=search_web('query')
        self.assertEqual(len(result['results']),1);self.assertEqual(result['results'][0]['url'],'https://example.org/docs')

    def test_multi_engine_search_keeps_verified_tls_and_filters_bad_links(self):
        with patch('mcp_network.DDGS') as search,patch('mcp_network.system_proxy',return_value=None):
            search.return_value.text.return_value=[{'title':'Docs','href':'https://docs.python.org/3/','body':'Python docs'},{'title':'bad','href':'javascript:alert(1)'}]
            result=search_web('python docs')
        self.assertEqual(len(result['results']),1)
        search.assert_called_once_with(proxy=None,timeout=7,verify=True)

    def test_calculator_never_executes_code_and_preserves_big_integers(self):
        self.assertEqual(calculate('2*(3+4)')['value'],14)
        self.assertEqual(calculate('sqrt(81)')['value'],9)
        self.assertEqual(calculate('10**20')['value'],'100000000000000000000')
        for text in ("__import__('os').system('whoami')",'open("x")','2**100000','().__class__'):
            with self.subTest(text=text),self.assertRaises((ValueError,SyntaxError)):calculate(text)

    def test_system_clock_does_not_use_network(self):
        with patch('mcp_network.fetch') as request:
            result=current_time()
        request.assert_not_called();self.assertRegex(result['date'],r'^\d{4}-\d{2}-\d{2}$');self.assertIn('星期',result['weekday'])

    def test_fake_dns_via_proxy_still_requires_public_real_ip(self):
        response=unittest.mock.Mock();response.json.return_value={'Answer':[{'type':1,'data':'127.0.0.1'}]}
        with patch('mcp_network.socket.getaddrinfo',return_value=[(2,1,6,'',('198.18.0.1',443))]),patch('mcp_network.system_proxy',return_value='http://127.0.0.1:7897'),patch('mcp_network.httpx.get',return_value=response):
            with self.assertRaises(ValueError):public_addresses('public.example')

    def test_redirect_private_destination_is_rejected(self):
        from unittest.mock import Mock
        first=Mock();first.getresponse.return_value.status=302;first.getresponse.return_value.getheader.return_value='https://127.0.0.1/private'
        second=PublicConnection('127.0.0.1')
        with patch('mcp_network.PublicConnection',side_effect=[first,second]):
            from mcp_network import fetch
            with self.assertRaises(ValueError):fetch('https://public.example')
