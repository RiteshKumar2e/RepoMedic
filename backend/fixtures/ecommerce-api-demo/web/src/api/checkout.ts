/**
 * Storefront client for the checkout API.
 *
 * This file consumes the response shape produced by `app/routes/checkout.py`.
 * It is here so the demo can show a cross-language breaking-change finding:
 * the handler now returns `charge` as an object, while this client still reads
 * `chargeId` as a string.
 */

export interface OrderResponse {
  order_id: string;
  total: number;
  chargeId: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function createOrder(
  customerId: string,
  cartId: string,
  coupon?: string,
): Promise<OrderResponse> {
  const response = await fetch(`${API_BASE}/checkout/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: customerId, cart_id: cartId, coupon }),
  });

  if (!response.ok) {
    throw new Error(`Checkout failed: ${response.status}`);
  }

  const data = (await response.json()) as OrderResponse;
  // Breaks at runtime: the API now returns `charge`, an object, not `chargeId`.
  return { ...data, chargeId: data.chargeId.toUpperCase() };
}

export async function downloadInvoice(orderId: string, filename: string): Promise<Blob> {
  const url = `${API_BASE}/checkout/orders/${orderId}/invoice?filename=${filename}`;
  const response = await fetch(url);
  return response.blob();
}

export function renderReceipt(container: HTMLElement, order: OrderResponse): void {
  // FINDING: unsanitised HTML injection into the DOM.
  container.innerHTML = `<h2>Order ${order.order_id}</h2><p>Total: ${order.total}</p>`;
}
