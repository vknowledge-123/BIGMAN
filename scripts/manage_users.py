"""Local operator CLI; never distributes passwords, TOTP secrets or broker data."""
import argparse
from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.accounts import Accounts, AccountError


def main():
    parser=argparse.ArgumentParser(description='Manage local scanner accounts. Run only on the admin server.')
    parser.add_argument('action',choices=['create-admin','reset-password','reset-mfa'])
    parser.add_argument('--email',required=True)
    args=parser.parse_args()
    accounts=Accounts(Path(__file__).resolve().parents[1]/'data/auth.sqlite3')
    try:
        if args.action=='reset-mfa':
            if input('Reset authenticator and revoke sessions for this account? Type RESET: ')!='RESET':
                return
            accounts.reset(args.email,mfa=True)
        else:
            password=getpass('Password (12–128 characters): ')
            if password!=getpass('Repeat password: '):
                raise AccountError('Passwords do not match.')
            if args.action=='create-admin':
                accounts.create(args.email,password,input('Display name: '),admin=True)
            else:
                accounts.reset(args.email,password=password)
        print('Account updated. Sign in through the app; authenticator setup is required if not enrolled.')
    except AccountError as exc:
        parser.exit(1,str(exc)+'\n')


if __name__=='__main__':
    main()
