public class revertedV {
    // naive rollback of the changed line (here it is the right fix)
    public static double snippet(int price, int qty) {
        int total = 0;
        int tax = 0;
        total = price * qty;
        tax = total / 10;
        total = total + tax;
        return total;
    }
}
