import sys

from chatreader import main
from chatreader.paths import parse_args

args = parse_args(sys.argv[1:])
main.main(args.home)
