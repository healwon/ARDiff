public class newV {
    // money in cents from now on (x100), so the threshold moves too
    public static double snippet(int hours) {
        int base = 0;
        int pay = 0;
        int bonus = 0;
        base = hours * 1000;
        pay = base + 500;
        if (pay > 40000) {
            bonus = 1;
        }
        return bonus;
    }
}
