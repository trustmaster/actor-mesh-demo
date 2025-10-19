#!/usr/bin/env python3
"""
Mock Customer API service for E2E testing.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler


class CustomerAPIHandler(BaseHTTPRequestHandler):
    """Mock Customer API request handler."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'status': 'healthy', 'service': 'customer-api'}
            self.wfile.write(json.dumps(response).encode())

        elif self.path.startswith('/customers/'):
            # Extract customer email from path
            customer_email = self.path.split('/')[-1]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'customer_id': 'CUST-12345',
                'profile': {
                    'first_name': 'Test',
                    'last_name': 'Customer',
                    'email': customer_email,
                    'phone': '+1-555-0123',
                    'tier': 'premium',
                    'registration_date': '2023-01-15',
                    'preferences': {
                        'communication_method': 'email',
                        'language': 'en'
                    }
                },
                'support_history': [
                    {
                        'ticket_id': 'TICK-001',
                        'date': '2024-01-10',
                        'issue': 'Delivery delay',
                        'resolution': 'Expedited shipping'
                    }
                ]
            }
            self.wfile.write(json.dumps(response).encode())

        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'error': 'Not found'}
            self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        """Disable request logging."""
        pass


def main():
    """Start the Customer API mock server."""
    port = 8001
    server = HTTPServer(('0.0.0.0', port), CustomerAPIHandler)
    print(f'Customer API mock server running on port {port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down Customer API mock server')
        server.shutdown()


if __name__ == '__main__':
    main()
