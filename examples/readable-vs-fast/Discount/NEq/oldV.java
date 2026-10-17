public class oldV {
    // readable: unit price per quantity tier
    public static double snippet(int qty) {
        int unit = 10;
        int total = 0;
        if (qty >= 10) {
            unit = 8;
        }
        if (qty >= 50) {
            unit = 7;
        }
        total = qty * unit;
        return total;
    }
}
