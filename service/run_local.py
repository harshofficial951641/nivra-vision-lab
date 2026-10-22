"""Start the local hotspot camera host without exposing the dashboard to the LAN."""
from run_usb import make_app, PORT

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(make_app(), host='127.0.0.1', port=PORT, access_log=False,
                ws_max_size=3_300_000)
