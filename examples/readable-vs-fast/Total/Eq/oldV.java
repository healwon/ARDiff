public class oldV {
    // readable: each amount computed from scratch
    public static double snippet(int price, int qty) {
        int subtotal = price * qty;
        int tax = price * qty / 10;
        int total = price * qty + tax;
        return total;
    }
}
