public class oldV {
    // readable: a bonus once the pay passes 405
    public static double snippet(int hours) {
        int base = 0;
        int pay = 0;
        int bonus = 0;
        base = hours * 10;
        pay = base + 5;
        if (pay > 405) {
            bonus = 1;
        }
        return bonus;
    }
}
