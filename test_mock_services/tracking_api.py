#!/usr/bin/env python3
"""
Mock Tracking API service for E2E testing.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler


class TrackingAPIHandler(BaseHTTPRequestHandler):
    """Mock Tracking API request handler."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'status': 'healthy', 'service': 'tracking-api'}
            self.wfile.write(json.dumps(response).encode())

        elif self.path.startswith('/tracking/'):
            # Extract tracking number from path
            tracking_number = self.path.split('/')[-1]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'tracking_number': tracking_number,
                'status': 'in_transit',
                'location': 'Distribution Center - Los Angeles, CA',
                'estimated_delivery': '2024-01-15',
                'last_updated': '2024-01-13T14:30:00Z',
                'tracking_history': [
                    {
                        'date': '2024-01-10T08:00:00Z',
                        'status': 'shipped',
                        'location': 'Fulfillment Center - San Francisco, CA',
                        'description': 'Package shipped from fulfillment center'
                    },
                    {
                        'date': '2024-01-11T12:00:00Z',
                        'status': 'in_transit',
                        'location': 'Sort Facility - Sacramento, CA',
                        'description': 'Package arrived at sort facility'
                    },
                    {
                        'date': '2024-01-12T09:30:00Z',
                        'status': 'in_transit',
                        'location': 'Distribution Center - Los Angeles, CA',
                        'description': 'Package arrived at distribution center'
                    },
                    {
                        'date': '2024-01-13T14:30:00Z',
                        'status': 'out_for_delivery',
                        'location': 'Local Delivery Hub - Beverly Hills, CA',
                        'description': 'Out for delivery'
                    }
                ],
                'delivery_instructions': 'Leave at front door if no one is home',
                'carrier': 'FastShip Express',
                'service_type': 'Standard Ground'
            }
            self.wfile.write(json.dumps(response).encode())

        elif self.path.startswith('/shipments'):
            # Handle bulk tracking queries
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'shipments': [
                    {
                        'tracking_number': 'TRACK-12345',
                        'status': 'in_transit',
                        'estimated_delivery': '2024-01-15',
                        'order_id': 'ORD-12345'
                    },
                    {
                        'tracking_number': 'TRACK-12346',
                        'status': 'delivered',
                        'estimated_delivery': '2024-01-12',
                        'order_id': 'ORD-12346'
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
    """Start the Tracking API mock server."""
    port = 8003
    server = HTTPServer(('0.0.0.0', port), TrackingAPIHandler)
    print(f'Tracking API mock server running on port {port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down Tracking API mock server')
        server.shutdown()


if __name__ == '__main__':
    main()
