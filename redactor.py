import json
import os
import urllib
import socket
import threading
from lxml import etree
from mongodb import get
from claudia_interpretator import create_dict_by_doc,  next_step
from claudia_compilator import start_compilator
from cache import ClaudiaCacheHandler



class claudiaRedactor:
    def __init__(self,  args,  mongo,  lock,  httpd):
        print('Redactor.')
        computer = socket.gethostname()
        
        document = ""
        formula = "<p>Upload a formula from a file.</p>"
        formula_text = urllib.quote(formula)
        for arg in args['data']:
            data = arg['data']
            if arg['name'] == '"formula"':
                formula_text = urllib.quote(data)
            elif arg['name'] == '"formula_reserve"\r':
                formula_text = data
            elif arg['name'] == '"document_text"\r': 
                document = data
            elif arg['name'] == '"document"':
                document = urllib.quote(data)
            else:
                print('Unknown name: ' + arg['name'])
        
        # debugger
        s = "Formula: No errors."
        bugs = '<div id="bugs">' + s + '</div>'
        
        #results
        s = "Here results of the formula will be..."
        results = '<div id="f_results">' + s + '</div>'
        
        if computer == 'noX540LJ':
            template_name = 'cci/viewer/redactor.html'
        else:
            template_name = '/home/andrey/work/Claudia/claudia/cci/viewer/redactor.html'
        template_file = open(template_name,  'r')
        template = template_file.read()
        template_file.close()
        template = template.replace('<document_results/>',  results)
        template = template.replace('<debugger/>',  bugs)
        template = template.replace('<document/>',  document)
        template = template.replace('<formula_text/>',  formula_text)
        self.site = template
        

class runClaudia:
    def __init__(self,  args, mongo, httpd):
        print('Run redactor.')
        cch = ClaudiaCacheHandler('cl_redactor')
        state = {}
        thread = threading.currentThread().getName()
        lock = httpd.mLocks[thread]
        
        req = urllib.unquote(args['args'])
        req = json.loads(req)
        formula = urllib.unquote(req['formula'])
        text = urllib.unquote(req['doc'])
        ticket = req['ticket']
        
        
        state['step'] = 'Generation of chunks...'
        lock.acquire()
        httpd.results[ticket] = state
        lock.release()
        print('state: ' + str(state))
        doc = self.generator_of_chunks(text,  mongo,  lock)
        if doc is None:
            self.site = 'File ' + text[5:] + ' is not found.'
            return
        
        formula_name = "Formula was generated by ClaudiaRedactor. " + "Date: Today."
        state['step'] = 'Compile the formula...'
        lock.acquire()
        httpd.results[ticket] = state
        lock.release()
        print('state: ' + str(state))
        code = start_compilator(formula,  formula_name)
        
        doc_data = create_dict_by_doc(doc)
        state['count_of_steps'] = code['count_of_steps']
        for n in range(code['count_of_steps'] + 1):
            lock.acquire()
            state['step'] = 'Apply the formula...'
            state['current_step'] = n
            print('Step: ' + str(n))
            httpd.results[ticket] = state
            lock.release()
            doc_data = next_step(doc_data,  code,  None,  None,  n,  mongo)
        #doc_data = for_one_doc(doc,  code,  mongo,  cch,  ticket,  lock)
        
        results = '<p class="res_paragraph">Diagnose:</p>'
        results += '<p>' + doc_data['data']['Formula diagnose'] + '</p>'
        if text[:5] == 'Doc #':
            lock.acquire()
            js = get('doc.json',  number_of_card = text[5:],  dataset='cci',  mongo = mongo)
            lock.release()
            print('state: ' + str(state))
            for key in js:
                if key.find('CHF') != -1:
                    results += '<p class="res_paragraph">Apriory:</p>'
                    results += '<p>' + str(key) + '</p>'
        results += '<p class="res_paragraph">Sentences with untrivial annotations:</p>'
        for sentence in doc_data['sentences']:
            if len(sentence['data']) < 2:
                continue
            attr = ''
            for key in sentence['data']:
                if key == 'reject':
                    continue
                attr += key + ': ' + sentence['data'][key] + '; '
            p = '<p class="sentence_attr"><b>Sentence attributes: </b>' + attr + '</p>'
            results += p
            sent = ''
            for chunk in sentence['chunks']:
                sent += chunk['text'] + ' '
            p = '<p class="res_sentence">' + sent + '</p>'
            results += p
        results += '<p> </p>'
        
        results += '<p class="res_paragraph">Document:</p>'
        for node in doc:
            results += node
        
        state['step'] = 'Ready.'
        state['res'] = results
        lock.acquire()
        cch.putValue(ticket,  state)
        lock.release()
        print('state: ' + '<document>')
        self.site = urllib.quote(json.dumps(results))


    def split_to_chunks(self,  text,  lock):
        computer = socket.gethostname()
        if computer == 'noX540LJ':
            return text
        else:
            in_file_name = 'tmp/text.txt'
            out_file_name = 'tmp/chunks.html'
            lock.acquire()
            in_file = open(in_file_name,  'w')
            in_file.write(text)
            in_file.close()
            lock.release()
            q_source = "java -jar /data/projects/Claudia/lib/hsconnector.jar"
            q = q_source + " < " + in_file_name + " > " + out_file_name
            #out,  err = subprocess.Popen(q + in_file_name, stdout=subprocess.PIPE, shell=True).communicate()
            os.system(q)
            lock.acquire()
            out_file = open(out_file_name,  'r')
            out = out_file.read()
            out_file.close()
            lock.release()
            out = out.replace('\r',  '')
            return out

    def generator_of_chunks(self,  text, mongo,  lock):
        if text[:5] == 'Doc #':
            number_of_card = text[5:]
            lock.acquire()
            nodes = get("doc.html",  number_of_card=number_of_card,  
                                            dataset='cci',  mongo=mongo)
            lock.release()
            if nodes is None:
                return
            doc = '\n'.join(nodes)
        else:
            doc = self.split_to_chunks(text,  lock)
        
        computer = socket.gethostname()
        if computer == 'noX540LJ':
            tmp_file = 'tmp/formula.cla'
        else:
            tmp_file = '/home/andrey/work/Claudia/claudia/tmp/formula.cla'
        file = open(tmp_file,  'w')
        file.write(doc)
        file.close()
        try:
            with open(tmp_file,  'rb') as inp:
                sHTML_Parser = etree.HTMLParser(remove_comments = True)
                tree = etree.parse(inp, sHTML_Parser)
                nodes = tree.xpath('/html/body/p')
        except IOError:
            print('No such file or directory: ' + tmp_file)
            return
        s_nodes = []
        for node in nodes:
            s_nodes.append(etree.tostring(node))
        return s_nodes


class redactorTicket:
    def __init__(self,  args,  mongo, httpd):
        thread = threading.currentThread()
        lock = httpd.mLocks[thread.getName()]
        lock.acquire()
        cch = ClaudiaCacheHandler('cl_redactor')
        ticket = cch.getFreeTicket()
        lock.release()
        self.site = urllib.quote(json.dumps(ticket))
        
class redactorProgress:
    def __init__(self,  args,  mongo,  httpd):
        print('progress')
        req = urllib.unquote(args['args'])
        req = json.loads(req)
        ticket = req['ticket']
        thread = threading.currentThread().getName()
        lock = httpd.mLocks[thread]
        res = None
        lock.acquire()
        if ticket in httpd.results:
            res = httpd.results[ticket]
            if res['step'] == 'Ready.':
                cch = ClaudiaCacheHandler('cl_redactor')
                res = cch.getValue(ticket)
        lock.release()
        if len(str(res)) < 100:
            print('progress: ' + str(res))
        if res is None:
            res = {}
        self.site = urllib.quote(json.dumps(res))
