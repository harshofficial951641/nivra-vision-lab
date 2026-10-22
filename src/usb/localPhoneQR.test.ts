import { describe, expect, it } from 'vitest'
import { localPhoneQR } from './localPhoneQR'
const qr = 'nivra-local://camera?host=172.20.10.1&port=8940#key=ABCD2345'
describe('local phone QR capabilities', () => {
  it('accepts only the fixed phone service with a private host and valid code', () => {
    expect(localPhoneQR(qr)).toEqual({ host: '172.20.10.1', code: 'ABCD2345' })
    for (const host of ['10.0.0.2', '172.16.0.2', '172.31.255.2', '192.168.1.3']) expect(localPhoneQR(qr.replace('172.20.10.1', host))?.host).toBe(host)
    for (const host of ['127.0.0.1', '8.8.8.8', '169.254.1.1', '172.32.1.1', '192.169.1.1', '10.999.0.1', '010.0.0.1', 'example.com', '[::1]']) expect(localPhoneQR(qr.replace('172.20.10.1', host))).toBeNull()
  })
  it('rejects URLs, role changes, duplicate fields, unknown fields and credential injection', () => {
    for (const value of [qr.replace('nivra-local:', 'https:'), qr.replace('://camera', '://guard'), qr.replace('://camera', '://user:pass@camera'), qr.replace('port=8940', 'port=80'), qr.replace('port=8940', 'port=8940&host=10.0.0.1'), qr.replace('port=8940', 'port=8940&url=https://evil.example'), qr + '&key=ABCD2345', qr + '&operator=anything', qr.replace('ABCD2345', 'ABCD01IO')]) expect(localPhoneQR(value)).toBeNull()
  })
  it('accepts at most eight unique private fallback candidates that include the main host', () => {
    expect(localPhoneQR(qr.replace('&port', '&hosts=172.20.10.1,192.168.1.2&port'))).toEqual({ host: '172.20.10.1', hosts: ['172.20.10.1', '192.168.1.2'], code: 'ABCD2345' })
    for (const hosts of ['192.168.1.2', '172.20.10.1,172.20.10.1', '172.20.10.1,8.8.8.8', '172.20.10.1,', ['172.20.10.1', ...Array.from({ length: 8 }, (_, i) => `10.0.0.${i + 1}`)].join(',')]) expect(localPhoneQR(qr.replace('&port', `&hosts=${hosts}&port`))).toBeNull()
  })
})
