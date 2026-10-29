public class newV {
    // three edits: operands swapped, tax from price * qty directly, terms swapped
    public static double snippet(int price, int qty) {
        int total = 0;
        int tax = 0;
        total = qty * price;
        tax = price * qty / 10;
        total = tax + total;
        return total;
    }
}
