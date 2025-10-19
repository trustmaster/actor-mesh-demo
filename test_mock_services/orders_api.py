#!/usr/bin/env python3
"""
Mock Orders API service for E2E testing.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler


class OrdersAPIHandler(BaseHTTPRequestHandler):
    """Mock Orders API request handler."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'status': 'healthy', 'service': 'orders-api'}
            self.wfile.write(json.dumps(response).encode())

        elif self.path.startswith('/orders'):
            # Parse query parameters if any
            customer_email = None
            if '?' in self.path:
                query_part = self.path.split('?')[1]
                params = dict(param.split('=') for param in query_part.split('&') if '=' in param)
                customer_email = params.get('customer_email')

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'orders': [
                    {
                        'order_id': 'ORD-12345',
                        'status': 'shipped',
                        'items': [
                            {
                                'product_id': 'PROD-001',
                                'name': 'Laptop Computer',
                                'quantity': 1,
                                'price': 999.99
                            }
                        ],
                        'shipping_address': {
                            'street': '123 Main St',
                            'city': 'Anytown',
                            'state': 'CA',
                            'zip': '12345'
                        },
                        'order_date': '2024-01-10',
                        'expected_delivery': '2024-01-15',
                        'total': 999.99,
                        'customer_email': customer_email or 'test@example.com'
                    },
                    {
                        'order_id': 'ORD-12346',
                        'status': 'processing',
                        'items': [
                            {
                                'product_id': 'PROD-002',
                                'name': 'Wireless Mouse',
                                'quantity': 2,
                                'price': 29.99
                            }
                        ],
                        'shipping_address': {
                            'street': '456 Oak Ave',
                            'city': 'Somewhere',
                            'state': 'NY',
                            'zip': '67890'
                        },
                        'order_date': '2024-01-12',
                        'expected_delivery': '2024-01-18',
                        'total': 59.98,
                        'customer_email': customer_email or 'test@example.com'
                    }
                ]
            }
            self.wfile.write(json.dumps(response).encode())

        elif self.path.startswith('/orders/'):
            # Get specific order by ID
            order_id = self.path.split('/')[-1]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'order_id': order_id,
                'status': 'shipped',
                'items': [
                    {
                        'product_id': 'PROD-001',
                        'name': 'Laptop Computer',
                        'quantity': 1,
                        'price': 999.99
                    }
                ],
                'shipping_address': {
                    'street': '123 Main St',
                    'city': 'Anytown',
                    'state': 'CA',
                    'zip': '12345'
                },
                'order_date': '2024-01-10',
                'expected_delivery': '2024-01-15',
                'total': 999.99,
                'tracking_number': 'TRACK-12345'
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
    """Start the Orders API mock server."""
    port = 8002
    server = HTTPServer(('0.0.0.0', port), OrdersAPIHandler)
    print(f'Orders API mock server running on port {port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down Orders API mock server')
        server.shutdown()


if __name__ == '__main__':
    main()
