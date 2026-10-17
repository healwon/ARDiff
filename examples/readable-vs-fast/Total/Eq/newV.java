public class newV {
    // fast: reuse the subtotal instead of multiplying again
    public static double snippet(int price, int qty) {
        int subtotal = price * qty;
        int tax = subtotal / 10;
        int total = subtotal + tax;
        return total;
    }
}
