#!/usr/bin/env python3

'''Unofficial CLI for the Wayback Machine's Save Page Now API.'''

__version__ = '0.2.1'

import asyncio
import collections
import sys

import click
import confuse
import httpx
import jsonlines
import tenacity


class Client(httpx.AsyncClient):
    def __init__(self, access_key, secret_key):
        super().__init__(base_url='https://web.archive.org/')
        self.headers['accept'] = 'application/json'
        self.headers['authorization'] = f'LOW {access_key}:{secret_key}'

    @tenacity.retry(wait=tenacity.wait_random_exponential(0.5, 60))
    async def request(self, method, url, **kwargs):
        r = await super().request(method, url, **kwargs)
        r.raise_for_status()
        return r


help = {'access_key': 'Get your account’s keys at '
                      'https://archive.org/account/s3.php',
        'capture_all': 'Capture a web page with errors (HTTP status=4xx or '
                       '5xx). By default SPN2 captures only status=200 '
                       'pages.',
        'capture_cookie': 'Use extra HTTP Cookie value when capturing the '
                          'target page.',
        'capture_outlinks': 'Capture web page outlinks automatically. This '
                            'also applies to PDF, JSON, RSS and MRSS feeds.',
        'capture_screenshot': 'Capture full page screenshot in PNG format.',
        'delay_wb_availability': 'The capture becomes available in the '
                                 'Wayback Machine after ~12 hours instead of '
                                 'immediately. This option help reduce the '
                                 'load on our systems. All API responses '
                                 'remain exactly the same when using this '
                                 'option.',
        'email_result': 'Send an email report of the captured URLs to the '
                        'user’s email.',
        'force_get': 'Force the use of a simple HTTP GET request to capture '
                     'the target URL. By default SPN2 does a HTTP HEAD on '
                     'the target URL to decide whether to use a headless '
                     'browser or a simple HTTP GET request. force_get '
                     'overrides this behaviour.',
        'if_not_archived_within': 'Capture web page only if the latest '
                                  'existing capture at the Archive is older '
                                  'than the <timedelta> limit.  Its  format '
                                  'could be any datetime expression like “3d '
                                  '5h 20m” or just a number of seconds, e.g. '
                                  '“120”. If there is a capture within the '
                                  'defined timedelta, SPN2 returns that as a '
                                  'recent capture. The default system '
                                  '<timedelta> is 30 min. When using 2 comma '
                                  'separated <timedelta> values, the first '
                                  'one applies to the main capture and the '
                                  'second one applies to outlinks.',
        'js_behavior_timeout': 'Run JS code for <N> seconds after page load '
                               'to trigger target page functionality like '
                               'image loading on mouse over, scroll down to '
                               'load more content, etc. The default system '
                               '<N> is 5 sec. More details on the JS code we '
                               'execute: '
                               'https://github.com/internetarchive/brozzler/blob/master/brozzler/behaviors.yaml ' # noqa
                               'WARNING: The max <N> value that applies is '
                               '30 sec. NOTE: If the target page doesn’t '
                               'have any JS you need to run, you can use '
                               'js_behavior_timeout=0 to speed up the '
                               'capture.',
        'outlinks_availability': 'Return the timestamp of the last capture '
                                 'for all outlinks.',
        'secret_key': 'Get your account’s keys at '
                      'https://archive.org/account/s3.php',
        'skip_first_archive': 'Skip checking if a capture is a first if you '
                              'don’t need this information. This will make '
                              'captures run faster.',
        'target_password': 'Use your own username and password in the target '
                           'page’s login forms.',
        'target_username': 'Use your own username and password in the target '
                           'page’s login forms.'}


@click.command()
@click.argument('urls', nargs=-1)
@click.option('--access-key', required=True,
              help=help['access_key'], metavar='<myaccesskey>')
@click.option('--secret-key', required=True,
              help=help['secret_key'], metavar='<mysecret>')
@click.option('--capture-all', type=int, is_flag=True,
              help=help['capture_all'])
@click.option('--capture-outlinks', type=int, is_flag=True,
              help=help['capture_outlinks'])
@click.option('--capture-screenshot', type=int, is_flag=True,
              help=help['capture_screenshot'])
@click.option('--delay-wb-availability', type=int, is_flag=True,
              help=help['delay_wb_availability'])
@click.option('--force-get', type=int, is_flag=True,
              help=help['force_get'])
@click.option('--skip-first-archive', type=int, is_flag=True,
              help=help['skip_first_archive'])
@click.option('--if-not-archived-within',
              help=help['if_not_archived_within'],
              metavar='<timedelta> or <timedelta>,<timedelta>')
@click.option('--outlinks-availability', type=int, is_flag=True,
              help=help['outlinks_availability'])
@click.option('--email-result', type=int, is_flag=True,
              help=help['email_result'])
@click.option('--js-behavior-timeout', type=int,
              help=help['js_behavior_timeout'], metavar='<N>')
@click.option('--capture-cookie',
              help=help['capture_cookie'], metavar='<XXX>')
@click.option('--target-username',
              help=help['target_username'], metavar='<XXX>')
@click.option('--target-password',
              help=help['target_password'], metavar='<YYY>')
@click.option('--input', '-i', 'file', type=click.File('r'),
              help='read URLs from or `-` for standard input',
              metavar='<file>')
@click.option('--output', '-o', type=click.File('w'), default=sys.stdout,
              help='write results to file',
              metavar='<file>')
@click.option('--wait/--no-wait', '-w/-W', default=False,
              help='wait for remote capture jobs to complete')
def _main(urls, access_key, secret_key, file, output, wait, **kwargs):

    '''Capture a web page as it appears now for use as a trusted citation in
       the future.'''

    # create 3 queues (i=input, v=verify, o=output)
    Q = collections.namedtuple('Q', ['i', 'v', 'o'])
    q = Q(i=asyncio.Queue(), v=asyncio.Queue(), o=asyncio.Queue())

    error = False

    async def loop():
        async def producer():
            for url in urls:
                await q.i.put(url)

            if file is not None:
                for url in file:
                    await q.i.put(url.rstrip('\r\n'))

            for queue in q:
                await queue.join()
                await queue.put(None)
                await queue.join()

        async def worker():
            async with Client(access_key, secret_key) as client:
                done = False
                while not done:
                    url = await q.i.get()
                    if url is None:
                        done = True
                    else:
                        data = {'url': url, **kwargs}
                        try:
                            r = (await client.post('save', data=data)).json()
                        except Exception as e:
                            await q.o.put((url, e))
                        else:
                            if wait and r.get('job_id') is not None:
                                await q.v.put((url, r))
                            else:
                                await q.o.put((url, r))
                    q.i.task_done()

        async def verifier():
            async with Client(access_key, secret_key) as client:
                done = False
                while not done:
                    item = await q.v.get()
                    if item is None:
                        done = True
                    else:
                        url, r = item

                        @tenacity.retry(wait=tenacity.wait_fixed(1))
                        async def get_status():
                            url = 'save/status/' + r["job_id"]
                            status = (await client.get(url)).json()
                            if status['status'] == 'pending':
                                raise ValueError
                            return status

                        status = await get_status()

                        await q.o.put((url, {**r, **status}))
                    q.v.task_done()

        async def logger():
            global error
            with jsonlines.Writer(output) as out:
                done = False
                while not done:
                    item = await q.o.get()
                    if item is None:
                        done = True
                    else:
                        url, r = item
                        if isinstance(r, Exception):
                            error = True
                            out.write({'url': url, 'result': None,
                                       'error': str(r)})
                        else:
                            try:
                                status = r['status']
                            except KeyError:
                                pass
                            else:
                                if wait:
                                    if status != 'success':
                                        error = True
                                else:
                                    if status not in {'pending', 'success'}:
                                        error = True
                            out.write(r)
                    q.o.task_done()

        async with asyncio.TaskGroup() as tg:
            tasks = set()
            tasks.add(tg.create_task(producer()))
            tasks.add(tg.create_task(worker()))
            tasks.add(tg.create_task(verifier()))
            tasks.add(tg.create_task(logger()))

    asyncio.run(loop())

    return int(error)


def main():
    return _main(auto_envvar_prefix='SPN',
                 default_map=confuse.Configuration('spn').flatten())
