"""Regression checks for complete pagination and alternative translation branches."""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import main

class ChapterListingTests(unittest.TestCase):
    def test_next_chapter_crosses_page_boundary_and_handles_last(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            items=[{'id':f'remanga-{i+1}','name':f'Глава {i+1}','group':'A'} for i in range(82)]
            main.save(root/'indexes/remanga-42-ru.json',{'items':items})
            with patch.object(main,'ROOT',root),patch.object(main,'all_chapters',side_effect=AssertionError('network used')):
                self.assertEqual(main.next_chapter('remanga-42','ru','remanga-80')['next'],items[80])
                self.assertIsNone(main.next_chapter('remanga-42','ru','remanga-82')['next'])

    def test_next_chapter_skips_duplicate_number_and_prefers_same_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            items=[dict(id=f'remanga-{i+1}',volume='1',number=n,group=g) for i,(n,g) in enumerate([('1','A'),('1','B'),('2','B'),('2','A'),('3','A')])]
            main.save(root/'indexes/remanga-42-ru.json',{'items':items})
            with patch.object(main,'ROOT',root):
                self.assertEqual(main.next_chapter('remanga-42','ru','remanga-1')['next'],items[3])

    def test_remanga_collects_short_pages_and_all_branches(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            main.save(root/'books/remanga-42.json',{'dir':'example'})
            def remote(path,params=None):
                if path.startswith('titles/example'):
                    return {'content':{'branches':[{'id':1,'count_chapters':3,'publishers':[{'name':'A'}]},{'id':2,'count_chapters':2,'publishers':[{'name':'B'}]}]}}
                data={(1,1):[{'id':11,'chapter':'1'},{'id':12,'chapter':'2'}],(1,2):[{'id':13,'chapter':'3'}],(2,1):[{'id':21,'chapter':'1'},{'id':22,'chapter':'4'}]}
                return {'content':data.get((params['branch_id'],params['page']),[])}
            with patch.object(main,'ROOT',root),patch.object(main,'remapi',side_effect=remote):
                all_items=main.chapter_listing('remanga-42','ru',0)
                self.assertEqual(all_items['branches'],2)
                self.assertEqual(all_items['total'],5)
                self.assertEqual({x['id'] for x in all_items['items']},{'remanga-11','remanga-12','remanga-13','remanga-21','remanga-22'})
                found=main.chapter_listing('remanga-42','ru',0,'Глава 4')
                self.assertEqual([x['id'] for x in found['items']],['remanga-22'])
                self.assertEqual(found['allTotal'],5)

    def test_mangadex_keeps_external_entries_and_uses_actual_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            responses=[]
            def remote(path,params):
                offset=params['offset'];responses.append(offset)
                if offset==0:
                    return {'total':3,'data':[{'id':'first','attributes':{'chapter':'1','pages':10},'relationships':[]},{'id':'external','attributes':{'chapter':'2','pages':0,'externalUrl':'https://example.org/chapter'},'relationships':[]}]}
                return {'total':3,'data':[{'id':'last','attributes':{'chapter':'3','pages':5},'relationships':[]}]}
            with patch.object(main,'ROOT',Path(directory)),patch.object(main,'api',side_effect=remote):
                items,_=main.all_chapters('example','ru')
            self.assertEqual(responses,[0,2])
            self.assertEqual(len(items),3)
            self.assertEqual(items[1]['external'],'https://example.org/chapter')

class RussianOfflineTests(unittest.TestCase):
    def test_search_survives_failed_source_and_removes_empty_cards(self):
        def rem(q,lang,offset):
            self.assertEqual(lang,'ru')
            return {'items':[{'id':'empty','name':'Empty','chapterCount':0},{'id':'ok','name':'Russian','source':'remanga','chapterCount':2}], 'total':2}
        with patch.object(main,'remsearch',side_effect=rem),patch.object(main,'search',side_effect=OSError('offline')),patch.object(main.sources,'search',side_effect=OSError('offline')):
            result=main.russian_search('test','en',0)
        self.assertEqual([b['id'] for b in result['items']],['ok'])
        self.assertEqual(len(result['warnings']),5)
        self.assertIsNone(result['error'])

    def test_complete_chapter_reads_without_network(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cid='remanga-42';folder=root/'chapters'/cid
            main.save(folder/'pages.json',{'id':cid,'urls':['https://example.org/page']})
            main.save(folder/'complete.json',{'pages':1})
            Image.new('RGB',(10,20)).save(folder/'0001.jpg')
            with patch.object(main,'ROOT',root),patch.object(main,'request',side_effect=AssertionError('network used')):
                self.assertEqual(main.pages(cid)['id'],cid)
                self.assertEqual(main.page(cid,0)['ratio'],2)

    def test_cached_chapter_list_survives_network_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            main.save(root/'indexes/remanga-42-ru.json',{'items':[{'id':'remanga-1','name':'Глава 1','group':'RU'}],'branches':1,'time':0,'revision':'0'})
            with patch.object(main,'ROOT',root),patch.object(main,'all_chapters',side_effect=OSError('offline')):
                result=main.chapter_listing('remanga-42','ru',0,revision='2')
            self.assertTrue(result['stale'])
            self.assertEqual(result['total'],1)
            self.assertEqual(result['revision'],'2')

if __name__=='__main__': unittest.main()
