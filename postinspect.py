#!/usr/bin/env python3

import argparse
from pprint import pprint
from wordpress_xmlrpc import Client, WordPressPost, WordPressTerm
from wordpress_xmlrpc.methods import media, posts, taxonomies

class Worker:
    def getPost(self):
        self.wp = Client(self.wordpress, self.wordpressUser, self.wordpressPass)
        
        post = self.wp.call(posts.GetPost(self.i))
        
#        pprint(vars(post._def['enclosure']))
        pprint(vars(post))


def main():
    context=Worker()
    
    parser = argparse.ArgumentParser(
        fromfile_prefix_chars='@'
    )

    parser.add_argument('--wordpress-url', dest='wordpress',
        help="""WordPress URL, preferably ending with ‘/xmlrpc.php’""")

    parser.add_argument('--wordpress-user', dest='wordpressUser',
        help="""WordPress username""")

    parser.add_argument('--wordpress-pass', dest='wordpressPass',
        help="""WordPress password""")

    parser.add_argument('i', type=str, 
                        help='post ID')

    args = parser.parse_args(namespace=context)
    
    context.getPost()

__name__ == '__main__' and main()

