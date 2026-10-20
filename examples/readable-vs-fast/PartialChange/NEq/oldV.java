public class oldV {
    // three edits, one of them changes the result
    public static double snippet(int price, int qty) {
        int subtotal = 0;
        int shipping = 0;
        int discount = 0;
        int total = 0;
        subtotal = price * qty;
        shipping = 5;
        if (qty >= 10) {
            discount = subtotal / 10;
        }
        total = subtotal - discount + shipping;
        return total;
    }
}
